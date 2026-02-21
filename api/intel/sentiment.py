"""
Sentiment Intel Layer

Sources (no auth required / free tier):
  1. StockTwits API  — /api/2/streams/symbol/{ticker}.json
  2. Reddit r/investing + r/stocks pushshift-style via reddit JSON API
  3. Yahoo Finance news headlines via yfinance (ticker.news)

Returns:
  {
    "sentiment_score": 0-100,
    "sentiment_signals": [...],
    "sentiment_bull_pct": float,       # % bullish on StockTwits
    "sentiment_sources": {
        "stocktwits": {...},
        "reddit": {...},
        "news": {...},
    }
  }
"""

import logging
import requests
import re
from datetime import datetime, timedelta
from collections import Counter

logger = logging.getLogger(__name__)

_STOCKTWITS_URL = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json?limit=30"
_REDDIT_URL = "https://www.reddit.com/r/{sub}/search.json?q={ticker}&restrict_sr=1&sort=new&limit=25&t=week"
_REDDIT_HEADERS = {"User-Agent": "CyberScreener/1.0 research@cyberscreener.io"}

# Bullish / bearish keyword sets for headline/post scoring
_BULLISH_KEYWORDS = {
    "beat", "beats", "surge", "surges", "rally", "rallies", "upgrade", "upgraded",
    "buy", "outperform", "overweight", "strong", "growth", "record", "raise",
    "raised", "upside", "momentum", "breakout", "bullish", "positive", "win",
    "partnership", "contract", "expansion", "ai", "artificial intelligence",
}
_BEARISH_KEYWORDS = {
    "miss", "misses", "missed", "decline", "declines", "downgrade", "downgraded",
    "sell", "underperform", "underweight", "weak", "loss", "losses", "cut",
    "cuts", "layoff", "layoffs", "breach", "hack", "lawsuit", "investigation",
    "bearish", "negative", "concern", "warning", "risk",
}


def _score_text(text: str) -> str:
    """Return 'bullish', 'bearish', or 'neutral' for a text snippet."""
    lower = text.lower()
    bull_hits = sum(1 for w in _BULLISH_KEYWORDS if w in lower)
    bear_hits = sum(1 for w in _BEARISH_KEYWORDS if w in lower)
    if bull_hits > bear_hits:
        return "bullish"
    elif bear_hits > bull_hits:
        return "bearish"
    return "neutral"


def _get_stocktwits(ticker_sym: str) -> dict:
    """Fetch recent StockTwits messages and compute bull/bear %."""
    result = {"bull_pct": None, "bear_pct": None, "message_count": 0, "status": "unavailable"}
    try:
        resp = requests.get(
            _STOCKTWITS_URL.format(ticker=ticker_sym),
            timeout=6,
        )
        if resp.status_code == 200:
            data = resp.json()
            messages = data.get("messages", [])
            if not messages:
                return result

            sentiments = []
            for m in messages:
                entities = m.get("entities", {})
                sent = entities.get("sentiment")
                if sent and sent.get("basic"):
                    sentiments.append(sent["basic"].lower())  # "Bullish" or "Bearish"

            if sentiments:
                bull = sum(1 for s in sentiments if s == "bullish")
                bear = sum(1 for s in sentiments if s == "bearish")
                total = len(sentiments)
                result["bull_pct"] = round(bull / total * 100, 1)
                result["bear_pct"] = round(bear / total * 100, 1)
                result["message_count"] = len(messages)
                result["sentiment_count"] = total
                result["status"] = "ok"
        elif resp.status_code == 404:
            result["status"] = "no_symbol"
        else:
            result["status"] = f"http_{resp.status_code}"

    except requests.exceptions.Timeout:
        result["status"] = "timeout"
    except Exception as e:
        logger.debug(f"StockTwits error for {ticker_sym}: {e}")
        result["status"] = "error"

    return result


def _get_reddit_sentiment(ticker_sym: str) -> dict:
    """Scrape Reddit search results for recent mention sentiment."""
    result = {"bull_count": 0, "bear_count": 0, "neutral_count": 0, "post_count": 0, "status": "unavailable"}
    try:
        subreddits = ["investing", "stocks", "wallstreetbets"]
        titles = []

        for sub in subreddits:
            try:
                url = _REDDIT_URL.format(sub=sub, ticker=ticker_sym)
                resp = requests.get(url, headers=_REDDIT_HEADERS, timeout=5)
                if resp.status_code == 200:
                    posts = resp.json().get("data", {}).get("children", [])
                    for p in posts:
                        title = p.get("data", {}).get("title", "")
                        if ticker_sym.upper() in title.upper() or ticker_sym.lower() in title.lower():
                            titles.append(title)
            except Exception:
                continue

        if not titles:
            result["status"] = "no_mentions"
            return result

        for title in titles:
            label = _score_text(title)
            result[f"{label}_count"] += 1

        result["post_count"] = len(titles)
        result["status"] = "ok"

    except Exception as e:
        logger.debug(f"Reddit error for {ticker_sym}: {e}")
        result["status"] = "error"

    return result


def _get_news_sentiment(ticker_obj, ticker_sym: str) -> dict:
    """Analyze news headlines from yfinance ticker.news."""
    result = {"bull_count": 0, "bear_count": 0, "neutral_count": 0, "article_count": 0, "status": "unavailable"}
    try:
        news = ticker_obj.news
        if not news:
            result["status"] = "no_news"
            return result

        # Only last 7 days
        cutoff = datetime.now() - timedelta(days=7)
        for item in news[:20]:
            pub_time = item.get("providerPublishTime", 0)
            if pub_time:
                try:
                    pub_dt = datetime.fromtimestamp(pub_time)
                    if pub_dt < cutoff:
                        continue
                except Exception:
                    pass

            title = item.get("title", "")
            summary = item.get("summary", "")
            text = f"{title} {summary}"
            label = _score_text(text)
            result[f"{label}_count"] += 1
            result["article_count"] += 1

        result["status"] = "ok"

    except Exception as e:
        logger.debug(f"News sentiment error for {ticker_sym}: {e}")
        result["status"] = "error"

    return result


def _compute_sentiment_score(st: dict, reddit: dict, news: dict) -> tuple[int, list, float | None]:
    """
    Compute sentiment_score (0-100) from multi-source data.

    Weights:
    - StockTwits (most direct, tagged sentiment): 50%
    - News headlines:                              30%
    - Reddit mentions:                             20%
    """
    score = 0
    signals = []
    composite_bull_pct = None

    # ── StockTwits (50 pts) ──
    if st.get("status") == "ok" and st.get("bull_pct") is not None:
        bull = st["bull_pct"]
        bear = st.get("bear_pct", 0)
        n = st.get("message_count", 0)
        composite_bull_pct = bull

        if bull >= 70:
            score += 50
            signals.append(f"🚀 StockTwits: {bull:.0f}% bullish ({n} messages)")
        elif bull >= 55:
            score += 35
            signals.append(f"📈 StockTwits: {bull:.0f}% bullish ({n} messages)")
        elif bull >= 45:
            score += 20  # Neutral
        elif bull <= 30:
            score += 0
            signals.append(f"🔴 StockTwits: {bull:.0f}% bullish / {bear:.0f}% bearish ({n} messages)")
        else:
            score += 10  # Mildly bearish

    else:
        score += 15  # No data — neutral assumption

    # ── News (30 pts) ──
    if news.get("status") == "ok":
        bull_n = news.get("bull_count", 0)
        bear_n = news.get("bear_count", 0)
        total_n = news.get("article_count", 0)

        if total_n > 0:
            news_bull_pct = bull_n / total_n * 100
            if news_bull_pct >= 70:
                score += 30
                signals.append(f"📰 News sentiment: {bull_n}/{total_n} bullish headlines")
            elif news_bull_pct >= 50:
                score += 20
                signals.append(f"📰 News sentiment: {bull_n}/{total_n} bullish, {bear_n} bearish")
            elif news_bull_pct >= 35:
                score += 12
            elif bear_n > bull_n * 2:
                score += 0
                signals.append(f"📰 Bearish news flow: {bear_n} negative vs {bull_n} positive headlines")
            else:
                score += 8
        else:
            score += 10
    else:
        score += 10  # No news = neutral

    # ── Reddit (20 pts) ──
    if reddit.get("status") == "ok":
        bull_r = reddit.get("bull_count", 0)
        bear_r = reddit.get("bear_count", 0)
        total_r = reddit.get("post_count", 0)

        if total_r > 0:
            reddit_bull_pct = bull_r / total_r * 100
            if reddit_bull_pct >= 70 and total_r >= 3:
                score += 20
                signals.append(f"💬 Reddit: {bull_r}/{total_r} bullish posts")
            elif reddit_bull_pct >= 50:
                score += 12
            elif bear_r > bull_r and total_r >= 3:
                score += 2
                signals.append(f"💬 Reddit: bearish skew ({bear_r} negative posts)")
            else:
                score += 8
        else:
            score += 8
    else:
        score += 8  # No Reddit data = slight neutral

    return min(score, 100), signals, composite_bull_pct


def analyze_sentiment(ticker_obj, ticker_sym: str) -> dict:
    """
    Main entry point for the sentiment intel layer.
    Called by scanner.run_scan() when enable_sentiment=True.
    """
    try:
        st = _get_stocktwits(ticker_sym)
        reddit = _get_reddit_sentiment(ticker_sym)
        news = _get_news_sentiment(ticker_obj, ticker_sym)

        sentiment_score, signals, bull_pct = _compute_sentiment_score(st, reddit, news)

        return {
            "sentiment_score": sentiment_score,
            "sentiment_signals": signals,
            "sentiment_bull_pct": bull_pct,
            "sentiment_sources": {
                "stocktwits": st,
                "reddit": reddit,
                "news": news,
            },
        }

    except Exception as e:
        logger.warning(f"Sentiment failed for {ticker_sym}: {e}")
        return {
            "sentiment_score": 0,
            "sentiment_signals": [],
            "sentiment_bull_pct": None,
            "sentiment_sources": {},
        }

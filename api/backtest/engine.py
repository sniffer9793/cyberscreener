"""
Backtest engine for CyberScreener.

Answers three key questions:
1. Did my scoring predict actual 30-day returns?
2. Which intelligence layers added real alpha?
3. What was the optimal entry timing vs. earnings?
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from db.models import get_db, get_all_scores_for_backtest, get_price_on_date
import json


def fetch_forward_returns(ticker, entry_date_str, periods=[7, 14, 30, 60]):
    """Fetch actual forward returns from entry date.

    Returns dict like {7: 2.3, 14: -1.1, 30: 5.4, 60: 8.2} (percent returns)
    """
    try:
        entry_date = datetime.strptime(entry_date_str[:10], "%Y-%m-%d")
        end_date = entry_date + timedelta(days=max(periods) + 5)

        t = yf.Ticker(ticker)
        hist = t.history(start=entry_date.strftime("%Y-%m-%d"),
                         end=end_date.strftime("%Y-%m-%d"))

        if hist.empty or len(hist) < 2:
            return None

        entry_price = hist["Close"].iloc[0]
        returns = {}

        for p in periods:
            # Find the trading day closest to p days out
            target_idx = min(p, len(hist) - 1)
            if target_idx > 0:
                future_price = hist["Close"].iloc[target_idx]
                returns[p] = round(((future_price / entry_price) - 1) * 100, 2)
            else:
                returns[p] = None

        return returns
    except Exception:
        return None


def backtest_score_vs_returns(days=180, forward_period=30):
    """
    Q1: Did my scoring predict actual returns?

    Groups tickers by score quintile and compares average forward returns.
    """
    scores = get_all_scores_for_backtest(days)
    if not scores:
        return {"error": "No historical data. Run scans for a few weeks first.", "data": []}

    # For each scored ticker, get the actual forward return
    results = []
    seen = set()  # Avoid duplicate ticker/date combos

    for s in scores:
        key = f"{s['ticker']}_{s['scan_date'][:10]}"
        if key in seen:
            continue
        seen.add(key)

        returns = fetch_forward_returns(s["ticker"], s["scan_date"], [forward_period])
        if returns and returns.get(forward_period) is not None:
            results.append({
                "ticker": s["ticker"],
                "scan_date": s["scan_date"],
                "lt_score": s["lt_score"],
                "opt_score": s["opt_score"],
                "entry_price": s["entry_price"],
                "forward_return": returns[forward_period],
                "sec_score": s["sec_score"],
                "sentiment_score": s["sentiment_score"],
                "whale_score": s["whale_score"],
            })

    if not results:
        return {"error": "Could not calculate forward returns. Need more historical data.", "data": []}

    df = pd.DataFrame(results)

    # Score quintile analysis
    analysis = {}

    for score_col, label in [("lt_score", "Long-Term Score"), ("opt_score", "Options Score")]:
        try:
            df["quintile"] = pd.qcut(df[score_col], q=5, labels=["Bottom 20%", "20-40%", "40-60%", "60-80%", "Top 20%"],
                                      duplicates="drop")
            quintile_stats = df.groupby("quintile").agg(
                avg_return=("forward_return", "mean"),
                median_return=("forward_return", "median"),
                win_rate=("forward_return", lambda x: (x > 0).mean() * 100),
                count=("forward_return", "count"),
                avg_score=(score_col, "mean"),
            ).round(2)

            analysis[label] = quintile_stats.to_dict("index")
        except Exception:
            analysis[label] = {"error": "Not enough data for quintile analysis"}

    # Correlation
    for score_col, label in [("lt_score", "lt_correlation"), ("opt_score", "opt_correlation")]:
        try:
            corr = df[score_col].corr(df["forward_return"])
            analysis[label] = round(corr, 4)
        except Exception:
            analysis[label] = None

    # Overall stats
    analysis["total_observations"] = len(results)
    analysis["date_range"] = {
        "start": min(r["scan_date"] for r in results),
        "end": max(r["scan_date"] for r in results),
    }
    analysis["forward_period_days"] = forward_period
    analysis["raw_data"] = results[:200]  # Cap for API response size

    return analysis


def backtest_layer_attribution(days=180, forward_period=30):
    """
    Q2: Which intelligence layers added real alpha?

    Compares returns when each layer's signal was bullish vs bearish vs absent.
    """
    scores = get_all_scores_for_backtest(days)
    if not scores:
        return {"error": "No historical data.", "data": []}

    results = []
    seen = set()

    for s in scores:
        key = f"{s['ticker']}_{s['scan_date'][:10]}"
        if key in seen:
            continue
        seen.add(key)

        returns = fetch_forward_returns(s["ticker"], s["scan_date"], [forward_period])
        if returns and returns.get(forward_period) is not None:
            results.append({**s, "forward_return": returns[forward_period]})

    if not results:
        return {"error": "No return data available.", "data": []}

    df = pd.DataFrame(results)
    attribution = {}

    # SEC Intelligence
    sec_bullish = df[df["sec_score"] > 0]
    sec_bearish = df[df["sec_score"] < 0]
    sec_neutral = df[df["sec_score"] == 0]
    attribution["sec_filings"] = {
        "bullish_signals": {
            "count": len(sec_bullish),
            "avg_return": round(sec_bullish["forward_return"].mean(), 2) if len(sec_bullish) > 0 else None,
            "win_rate": round((sec_bullish["forward_return"] > 0).mean() * 100, 1) if len(sec_bullish) > 0 else None,
        },
        "bearish_signals": {
            "count": len(sec_bearish),
            "avg_return": round(sec_bearish["forward_return"].mean(), 2) if len(sec_bearish) > 0 else None,
            "win_rate": round((sec_bearish["forward_return"] > 0).mean() * 100, 1) if len(sec_bearish) > 0 else None,
        },
        "no_signal": {
            "count": len(sec_neutral),
            "avg_return": round(sec_neutral["forward_return"].mean(), 2) if len(sec_neutral) > 0 else None,
        },
        "alpha": None,
    }
    if len(sec_bullish) > 0 and len(sec_neutral) > 0:
        attribution["sec_filings"]["alpha"] = round(
            sec_bullish["forward_return"].mean() - sec_neutral["forward_return"].mean(), 2
        )

    # Insider Buying
    insider_buy = df[df["insider_buys_30d"] > 0]
    no_insider = df[df["insider_buys_30d"] == 0]
    attribution["insider_buying"] = {
        "with_insider_buys": {
            "count": len(insider_buy),
            "avg_return": round(insider_buy["forward_return"].mean(), 2) if len(insider_buy) > 0 else None,
            "win_rate": round((insider_buy["forward_return"] > 0).mean() * 100, 1) if len(insider_buy) > 0 else None,
        },
        "no_insider_buys": {
            "count": len(no_insider),
            "avg_return": round(no_insider["forward_return"].mean(), 2) if len(no_insider) > 0 else None,
        },
        "alpha": None,
    }
    if len(insider_buy) > 0 and len(no_insider) > 0:
        attribution["insider_buying"]["alpha"] = round(
            insider_buy["forward_return"].mean() - no_insider["forward_return"].mean(), 2
        )

    # Sentiment
    sent_bullish = df[df["sentiment_bull_pct"].notna() & (df["sentiment_bull_pct"] >= 65)]
    sent_bearish = df[df["sentiment_bull_pct"].notna() & (df["sentiment_bull_pct"] <= 35)]
    sent_none = df[df["sentiment_bull_pct"].isna()]
    attribution["sentiment"] = {
        "bullish": {
            "count": len(sent_bullish),
            "avg_return": round(sent_bullish["forward_return"].mean(), 2) if len(sent_bullish) > 0 else None,
            "win_rate": round((sent_bullish["forward_return"] > 0).mean() * 100, 1) if len(sent_bullish) > 0 else None,
        },
        "bearish": {
            "count": len(sent_bearish),
            "avg_return": round(sent_bearish["forward_return"].mean(), 2) if len(sent_bearish) > 0 else None,
        },
        "not_available": {"count": len(sent_none)},
        "alpha": None,
    }
    if len(sent_bullish) > 0 and len(sent_bearish) > 0:
        attribution["sentiment"]["alpha"] = round(
            sent_bullish["forward_return"].mean() - sent_bearish["forward_return"].mean(), 2
        )

    # Whale Flow (put/call ratio)
    whale_bullish = df[df["pc_ratio"].notna() & (df["pc_ratio"] < 0.7)]
    whale_bearish = df[df["pc_ratio"].notna() & (df["pc_ratio"] > 1.3)]
    attribution["whale_flow"] = {
        "bullish_flow": {
            "count": len(whale_bullish),
            "avg_return": round(whale_bullish["forward_return"].mean(), 2) if len(whale_bullish) > 0 else None,
        },
        "bearish_flow": {
            "count": len(whale_bearish),
            "avg_return": round(whale_bearish["forward_return"].mean(), 2) if len(whale_bearish) > 0 else None,
        },
        "alpha": None,
    }
    if len(whale_bullish) > 0 and len(whale_bearish) > 0:
        attribution["whale_flow"]["alpha"] = round(
            whale_bullish["forward_return"].mean() - whale_bearish["forward_return"].mean(), 2
        )

    attribution["total_observations"] = len(results)
    attribution["forward_period_days"] = forward_period

    return attribution


def backtest_earnings_timing(days=180):
    """
    Q3: What was the optimal entry timing vs. earnings?

    Analyzes returns based on when you entered relative to earnings date.
    """
    scores = get_all_scores_for_backtest(days)
    if not scores:
        return {"error": "No historical data.", "data": []}

    # Filter to only entries with earnings dates
    with_earnings = [s for s in scores if s.get("days_to_earnings") is not None and s["days_to_earnings"] > 0]

    if not with_earnings:
        return {"error": "No entries with earnings date data.", "data": []}

    results = []
    seen = set()

    for s in with_earnings:
        key = f"{s['ticker']}_{s['scan_date'][:10]}"
        if key in seen:
            continue
        seen.add(key)

        # Get returns at multiple horizons
        returns = fetch_forward_returns(s["ticker"], s["scan_date"], [7, 14, 30])
        if returns:
            results.append({
                "ticker": s["ticker"],
                "scan_date": s["scan_date"],
                "days_to_earnings": s["days_to_earnings"],
                "opt_score": s["opt_score"],
                "iv_30d": s["iv_30d"],
                "return_7d": returns.get(7),
                "return_14d": returns.get(14),
                "return_30d": returns.get(30),
            })

    if not results:
        return {"error": "Could not match earnings entries with returns.", "data": []}

    df = pd.DataFrame(results)

    # Bucket by days to earnings
    buckets = {
        "1-7 days": df[(df["days_to_earnings"] >= 1) & (df["days_to_earnings"] <= 7)],
        "8-14 days": df[(df["days_to_earnings"] >= 8) & (df["days_to_earnings"] <= 14)],
        "15-30 days": df[(df["days_to_earnings"] >= 15) & (df["days_to_earnings"] <= 30)],
        "31-45 days": df[(df["days_to_earnings"] >= 31) & (df["days_to_earnings"] <= 45)],
    }

    timing = {}
    for label, bucket in buckets.items():
        if len(bucket) == 0:
            timing[label] = {"count": 0}
            continue

        timing[label] = {
            "count": len(bucket),
            "avg_return_7d": round(bucket["return_7d"].dropna().mean(), 2) if bucket["return_7d"].notna().any() else None,
            "avg_return_14d": round(bucket["return_14d"].dropna().mean(), 2) if bucket["return_14d"].notna().any() else None,
            "avg_return_30d": round(bucket["return_30d"].dropna().mean(), 2) if bucket["return_30d"].notna().any() else None,
            "avg_iv": round(bucket["iv_30d"].dropna().mean(), 1) if bucket["iv_30d"].notna().any() else None,
            "avg_opt_score": round(bucket["opt_score"].mean(), 1),
            "win_rate_14d": round((bucket["return_14d"].dropna() > 0).mean() * 100, 1) if bucket["return_14d"].notna().any() else None,
        }

    # Best entry window
    best_window = None
    best_return = -999
    for label, stats in timing.items():
        if stats.get("avg_return_14d") is not None and stats["avg_return_14d"] > best_return:
            best_return = stats["avg_return_14d"]
            best_window = label

    return {
        "timing_buckets": timing,
        "best_entry_window": best_window,
        "best_avg_14d_return": best_return if best_window else None,
        "total_earnings_plays": len(results),
        "raw_data": results[:100],
    }


def run_full_backtest(days=180, forward_period=30):
    """Run all three backtest analyses and return combined results."""
    return {
        "score_vs_returns": backtest_score_vs_returns(days, forward_period),
        "layer_attribution": backtest_layer_attribution(days, forward_period),
        "earnings_timing": backtest_earnings_timing(days),
        "generated_at": datetime.now().isoformat(),
        "params": {"lookback_days": days, "forward_period": forward_period},
    }

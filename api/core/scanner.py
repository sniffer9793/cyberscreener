"""
Core scanner — headless version of CyberScreener scanning logic.
Can be run by the API server, scheduler, or CLI.
"""

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
# TICKER UNIVERSE
# ─────────────────────────────────────────────

CYBER_UNIVERSE = {
    "Platform Giants": ["CRWD", "PANW", "FTNT", "ZS", "CSCO"],
    "Identity & Access (IAM)": ["OKTA", "CYBR", "SAIL"],
    "Cloud & Network Security": ["NET", "AKAM", "CHKP", "VRNS", "QLYS", "TENB", "RPD"],
    "AI-Powered / Next-Gen": ["S", "DDOG", "MSFT", "GOOGL"],
    "Endpoint Detection (EDR/XDR)": ["CRWD", "S", "AVGO", "GEN"],
    "Threat Intel / IR": ["OTEX", "RDWR"],
    "Enterprise GRC": ["QLYS", "TENB", "RPD", "IBM"],
    "Network Hardware / Firewall": ["FTNT", "CHKP", "NTCT", "ATEN"],
    "Data Security": ["VRNS"],
    "Gov / Defense Cyber": ["CACI", "LDOS", "SAIC", "BAH", "BBAI", "PLTR"],
    "Mid/Small Cap Plays": ["SCWX", "TELOS", "OSPN", "JAMF", "DT", "ESTC", "ZI"],
}

ALL_TICKERS = sorted(list(set(t for tickers in CYBER_UNIVERSE.values() for t in tickers)))


def fetch_ticker_data(ticker):
    """Fetch all relevant data for a single ticker."""
    try:
        t = yf.Ticker(ticker)
        info = t.info

        hist_1y = t.history(period="1y")
        if hist_1y.empty or len(hist_1y) < 20:
            return None

        price = hist_1y['Close'].iloc[-1]
        price_4w_ago = hist_1y['Close'].iloc[-21] if len(hist_1y) >= 21 else price
        price_13w_ago = hist_1y['Close'].iloc[-63] if len(hist_1y) >= 63 else price
        price_52w_high = hist_1y['High'].max()
        price_52w_low = hist_1y['Low'].min()
        price_1y_ago = hist_1y['Close'].iloc[0]

        avg_vol_20d = hist_1y['Volume'].tail(20).mean()
        avg_vol_5d = hist_1y['Volume'].tail(5).mean()
        vol_ratio = avg_vol_5d / avg_vol_20d if avg_vol_20d > 0 else 1.0

        close = hist_1y['Close']
        sma_20 = close.rolling(20).mean().iloc[-1]
        sma_50 = close.rolling(50).mean().iloc[-1]
        sma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None

        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = (100 - (100 / (1 + rs))).iloc[-1]

        rolling_std = close.rolling(20).std().iloc[-1]
        bb_width = (rolling_std * 4) / sma_20 * 100 if sma_20 > 0 else 0

        market_cap = info.get('marketCap', 0)
        revenue = info.get('totalRevenue', 0)
        fcf = info.get('freeCashflow', 0)
        revenue_growth = info.get('revenueGrowth', 0)
        gross_margins = info.get('grossMargins', 0)
        ps_ratio = info.get('priceToSalesTrailing12Months', None)
        pe_ratio = info.get('trailingPE', None)
        beta = info.get('beta', 1.0)
        short_percent = info.get('shortPercentOfFloat', 0) or 0

        # Earnings date
        earnings_date = None
        try:
            ed_df = t.get_earnings_dates(limit=4)
            if ed_df is not None and not ed_df.empty:
                now = pd.Timestamp.now(tz=ed_df.index[0].tzinfo) if ed_df.index[0].tzinfo else pd.Timestamp.now()
                future_dates = ed_df[ed_df.index >= now]
                if not future_dates.empty:
                    earnings_date = future_dates.index[0]
                else:
                    earnings_date = ed_df.index[0]
        except Exception:
            pass

        days_to_earnings = None
        if earnings_date is not None:
            try:
                ed = earnings_date.date() if hasattr(earnings_date, 'date') else pd.Timestamp(earnings_date).date()
                days_to_earnings = (ed - datetime.today().date()).days
            except Exception:
                pass

        iv_30d = None
        try:
            options_dates = t.options
            if options_dates:
                nearest = options_dates[0]
                opt_chain = t.option_chain(nearest)
                calls = opt_chain.calls
                if not calls.empty and 'impliedVolatility' in calls.columns:
                    iv_30d = calls['impliedVolatility'].median() * 100
        except Exception:
            pass

        perf_1y = ((price / price_1y_ago) - 1) * 100 if price_1y_ago > 0 else 0
        perf_3m = ((price / price_13w_ago) - 1) * 100 if price_13w_ago > 0 else 0
        pct_from_high = ((price / price_52w_high) - 1) * 100

        return {
            "ticker": ticker,
            "price": round(price, 2),
            "market_cap": market_cap,
            "market_cap_b": round(market_cap / 1e9, 1) if market_cap else None,
            "revenue_b": round(revenue / 1e9, 2) if revenue else None,
            "revenue_growth_pct": round(revenue_growth * 100, 1) if revenue_growth else None,
            "gross_margin_pct": round(gross_margins * 100, 1) if gross_margins else None,
            "fcf_m": round(fcf / 1e6, 0) if fcf else None,
            "ps_ratio": round(ps_ratio, 1) if ps_ratio else None,
            "pe_ratio": round(pe_ratio, 1) if pe_ratio else None,
            "beta": round(beta, 2) if beta else None,
            "short_pct": round(short_percent * 100, 1),
            "rsi": round(rsi, 1),
            "sma_20": round(sma_20, 2),
            "sma_50": round(sma_50, 2),
            "sma_200": round(sma_200, 2) if sma_200 else None,
            "bb_width": round(bb_width, 1),
            "vol_ratio": round(vol_ratio, 2),
            "perf_1y": round(perf_1y, 1),
            "perf_3m": round(perf_3m, 1),
            "pct_from_52w_high": round(pct_from_high, 1),
            "price_52w_high": round(price_52w_high, 2),
            "price_52w_low": round(price_52w_low, 2),
            "iv_30d": round(iv_30d, 1) if iv_30d else None,
            "days_to_earnings": days_to_earnings,
            "price_above_sma20": price > sma_20,
            "price_above_sma50": price > sma_50,
            "price_above_sma200": price > sma_200 if sma_200 else None,
        }
    except Exception:
        return None


def score_long_term(row):
    """Score a stock for long-term value."""
    score = 0
    reasons = []

    rg = row.get("revenue_growth_pct") or 0
    if rg > 25: score += 30; reasons.append(f"🚀 Strong revenue growth ({rg}%)")
    elif rg > 15: score += 15; reasons.append(f"📈 Solid revenue growth ({rg}%)")
    elif rg > 0: score += 5
    else: score -= 10; reasons.append("⚠️ Negative/no revenue growth")

    ps = row.get("ps_ratio") or 999
    if ps < 5 and rg > 15: score += 25; reasons.append(f"💎 Low P/S ({ps}x) with high growth")
    elif ps < 10 and rg > 20: score += 15; reasons.append(f"✅ Reasonable P/S ({ps}x) for growth rate")
    elif ps > 30: score -= 10; reasons.append(f"💸 Elevated P/S ({ps}x)")

    gm = row.get("gross_margin_pct") or 0
    if gm > 75: score += 20; reasons.append(f"💰 Excellent gross margins ({gm}%)")
    elif gm > 60: score += 10; reasons.append(f"✅ Good gross margins ({gm}%)")
    elif gm < 40: score -= 10; reasons.append(f"⚠️ Low gross margins ({gm}%)")

    fcf = row.get("fcf_m") or 0
    if fcf > 500: score += 20; reasons.append(f"💵 Strong FCF (${fcf:.0f}M)")
    elif fcf > 0: score += 10; reasons.append(f"✅ FCF positive (${fcf:.0f}M)")
    else: score -= 5; reasons.append(f"🔴 FCF negative (${fcf:.0f}M)")

    disc = row.get("pct_from_52w_high") or 0
    if disc < -30: score += 15; reasons.append(f"🏷️ Down {abs(disc):.0f}% from 52w high — potential value")
    elif disc < -15: score += 8; reasons.append(f"🏷️ Down {abs(disc):.0f}% from 52w high")

    return score, reasons


def score_options(row):
    """Score a stock for short-term options play."""
    score = 0
    reasons = []

    dte = row.get("days_to_earnings")
    if dte is not None:
        if 5 <= dte <= 14: score += 35; reasons.append(f"🎯 Earnings in {dte} days — prime options window")
        elif 15 <= dte <= 30: score += 25; reasons.append(f"📅 Earnings in {dte} days")
        elif 1 <= dte <= 4: score += 15; reasons.append(f"⚡ Earnings imminent ({dte} days)")

    iv = row.get("iv_30d") or 0
    if iv > 60: score += 20; reasons.append(f"🌋 High IV ({iv:.0f}%)")
    elif iv > 40: score += 10; reasons.append(f"📊 Elevated IV ({iv:.0f}%)")

    vr = row.get("vol_ratio") or 1
    if vr > 2.0: score += 20; reasons.append(f"🔥 Volume spike ({vr:.1f}x avg)")
    elif vr > 1.5: score += 10; reasons.append(f"📈 Elevated volume ({vr:.1f}x avg)")

    rsi = row.get("rsi") or 50
    if rsi < 30: score += 15; reasons.append(f"🟢 Oversold RSI ({rsi:.0f})")
    elif rsi > 70: score += 10; reasons.append(f"🔴 Overbought RSI ({rsi:.0f})")

    bb = row.get("bb_width") or 999
    if bb < 10: score += 15; reasons.append(f"🗜️ BB squeeze ({bb:.1f}%)")
    elif bb < 15: score += 8; reasons.append(f"📉 Tight BB ({bb:.1f}%)")

    beta_val = row.get("beta") or 1
    if beta_val > 1.5: score += 10; reasons.append(f"⚡ High beta ({beta_val})")

    short_pct = row.get("short_pct") or 0
    if short_pct > 10: score += 10; reasons.append(f"📌 High short interest ({short_pct}%)")

    return score, reasons


def run_scan(tickers=None, enable_sec=True, callback=None):
    """
    Run a full scan. Returns list of scored results.

    callback: optional function(ticker, i, total) for progress reporting
    """
    if tickers is None:
        tickers = ALL_TICKERS

    results = []
    for i, ticker in enumerate(tickers):
        if callback:
            callback(ticker, i, len(tickers))

        data = fetch_ticker_data(ticker)
        if data:
            lt_score, lt_reasons = score_long_term(data)
            opt_score, opt_reasons = score_options(data)
            data["lt_score"] = lt_score
            data["lt_reasons"] = lt_reasons
            data["opt_score"] = opt_score
            data["opt_reasons"] = opt_reasons
            data["sec_intel"] = None
            data["sentiment"] = None
            data["whale_flow"] = None
            results.append(data)

        time.sleep(0.15)  # Rate limiting

    return results

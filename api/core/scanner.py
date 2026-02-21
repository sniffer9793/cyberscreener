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


# ─────────────────────────────────────────────
# OPTIONS PLAY BUILDER
# ─────────────────────────────────────────────

def fetch_options_chain(ticker):
    """Fetch full options chain data for play building."""
    try:
        t = yf.Ticker(ticker)
        expiry_dates = t.options
        if not expiry_dates:
            return None

        chains = []
        for exp in expiry_dates[:6]:
            try:
                chain = t.option_chain(exp)
                for _, row in chain.calls.iterrows():
                    chains.append({
                        "type": "call",
                        "expiry": exp,
                        "strike": row["strike"],
                        "lastPrice": row.get("lastPrice", 0),
                        "bid": row.get("bid", 0),
                        "ask": row.get("ask", 0),
                        "volume": row.get("volume", 0) or 0,
                        "openInterest": row.get("openInterest", 0) or 0,
                        "iv": row.get("impliedVolatility", 0) or 0,
                        "inTheMoney": row.get("inTheMoney", False),
                    })
                for _, row in chain.puts.iterrows():
                    chains.append({
                        "type": "put",
                        "expiry": exp,
                        "strike": row["strike"],
                        "lastPrice": row.get("lastPrice", 0),
                        "bid": row.get("bid", 0),
                        "ask": row.get("ask", 0),
                        "volume": row.get("volume", 0) or 0,
                        "openInterest": row.get("openInterest", 0) or 0,
                        "iv": row.get("impliedVolatility", 0) or 0,
                        "inTheMoney": row.get("inTheMoney", False),
                    })
            except Exception:
                continue

        return chains if chains else None
    except Exception:
        return None


def calc_expected_move(price, iv, days):
    """Calculate expected price move based on IV and days to expiry."""
    if not iv or not days or days <= 0:
        return 0
    return price * (iv / 100) * np.sqrt(days / 365)


def find_best_strike(chains, option_type, expiry, price, target_delta="atm"):
    """Find the best strike for a given setup.
    target_delta: 'atm', 'otm_near' (~5% OTM), 'otm_far' (~10% OTM), 'itm_near' (~5% ITM)
    """
    filtered = [c for c in chains if c["type"] == option_type and c["expiry"] == expiry]
    if not filtered:
        return None

    if target_delta == "atm":
        return min(filtered, key=lambda x: abs(x["strike"] - price))
    elif target_delta == "otm_near":
        if option_type == "call":
            otm = [c for c in filtered if c["strike"] > price]
            target = price * 1.05
        else:
            otm = [c for c in filtered if c["strike"] < price]
            target = price * 0.95
        return min(otm, key=lambda x: abs(x["strike"] - target)) if otm else None
    elif target_delta == "otm_far":
        if option_type == "call":
            otm = [c for c in filtered if c["strike"] > price]
            target = price * 1.10
        else:
            otm = [c for c in filtered if c["strike"] < price]
            target = price * 0.90
        return min(otm, key=lambda x: abs(x["strike"] - target)) if otm else None
    elif target_delta == "itm_near":
        if option_type == "call":
            itm = [c for c in filtered if c["strike"] < price]
            target = price * 0.97
        else:
            itm = [c for c in filtered if c["strike"] > price]
            target = price * 1.03
        return min(itm, key=lambda x: abs(x["strike"] - target)) if itm else None
    return None


def find_best_expiry(chains, days_to_earnings=None):
    """Find the ideal expiry date based on catalyst timing."""
    expiries = sorted(set(c["expiry"] for c in chains))
    if not expiries:
        return None, None

    today = datetime.today().date()

    if days_to_earnings and days_to_earnings > 0:
        earnings_date = today + timedelta(days=days_to_earnings)
        post_earnings = [e for e in expiries
                         if datetime.strptime(e, "%Y-%m-%d").date() > earnings_date]
        if post_earnings:
            return post_earnings[0], "post-earnings"

    target_dte = 35
    best = min(expiries, key=lambda e: abs((datetime.strptime(e, "%Y-%m-%d").date() - today).days - target_dte))
    return best, "standard"


def generate_plays(ticker, price, chains, days_to_earnings=None, rsi=50, iv_30d=None,
                   price_above_sma20=True, price_above_sma50=True, perf_3m=0):
    """Generate specific options plays based on the setup."""
    plays = []
    if not chains or not price:
        return plays

    expiry, expiry_reason = find_best_expiry(chains, days_to_earnings)
    if not expiry:
        return plays

    exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
    dte = (exp_date - datetime.today().date()).days
    expected_move = calc_expected_move(price, iv_30d or 30, dte)

    # Determine directional bias
    bullish_signals = 0
    bearish_signals = 0
    if rsi and rsi < 35:
        bullish_signals += 2
    elif rsi and rsi > 70:
        bearish_signals += 1
    if price_above_sma20:
        bullish_signals += 1
    if price_above_sma50:
        bullish_signals += 1
    if perf_3m and perf_3m > 10:
        bullish_signals += 1
    elif perf_3m and perf_3m < -10:
        bearish_signals += 1

    is_earnings_play = days_to_earnings is not None and 1 <= days_to_earnings <= 30
    is_high_iv = (iv_30d or 0) > 50
    bias = "bullish" if bullish_signals > bearish_signals else "bearish" if bearish_signals > bullish_signals else "neutral"

    # ──── PLAY 1: Directional (Long Calls or Puts) ────
    if bias == "bullish":
        strike_opt = find_best_strike(chains, "call", expiry, price, "otm_near")
        if strike_opt:
            mid_price = (strike_opt["bid"] + strike_opt["ask"]) / 2 if strike_opt["ask"] > 0 else strike_opt["lastPrice"]
            breakeven = strike_opt["strike"] + mid_price
            max_loss = mid_price * 100
            pct_to_breakeven = ((breakeven / price) - 1) * 100

            plays.append({
                "strategy": "Long Call",
                "emoji": "📈",
                "direction": "Bullish",
                "action": f"BUY {ticker} ${strike_opt['strike']:.0f} Call",
                "expiry": expiry,
                "dte": dte,
                "strike": strike_opt["strike"],
                "entry_price": round(mid_price, 2),
                "bid": strike_opt["bid"],
                "ask": strike_opt["ask"],
                "breakeven": round(breakeven, 2),
                "pct_to_breakeven": round(pct_to_breakeven, 1),
                "max_loss": round(max_loss, 0),
                "max_gain": "Unlimited",
                "volume": int(strike_opt["volume"]),
                "open_interest": int(strike_opt["openInterest"]),
                "iv": round(strike_opt["iv"] * 100, 1),
                "rationale": f"Bullish bias — RSI {rsi:.0f}, {'above' if price_above_sma20 else 'below'} SMA20. "
                             f"{'Earnings catalyst in ' + str(days_to_earnings) + 'd. ' if is_earnings_play else ''}"
                             f"Expected move: ±${expected_move:.2f} ({expected_move/price*100:.1f}%)",
                "risk_notes": "Max loss limited to premium paid. Consider selling before expiry to capture time value."
            })

    elif bias == "bearish":
        strike_opt = find_best_strike(chains, "put", expiry, price, "otm_near")
        if strike_opt:
            mid_price = (strike_opt["bid"] + strike_opt["ask"]) / 2 if strike_opt["ask"] > 0 else strike_opt["lastPrice"]
            breakeven = strike_opt["strike"] - mid_price
            max_loss = mid_price * 100

            plays.append({
                "strategy": "Long Put",
                "emoji": "📉",
                "direction": "Bearish",
                "action": f"BUY {ticker} ${strike_opt['strike']:.0f} Put",
                "expiry": expiry,
                "dte": dte,
                "strike": strike_opt["strike"],
                "entry_price": round(mid_price, 2),
                "bid": strike_opt["bid"],
                "ask": strike_opt["ask"],
                "breakeven": round(breakeven, 2),
                "pct_to_breakeven": round(((price - breakeven) / price) * 100, 1),
                "max_loss": round(max_loss, 0),
                "max_gain": f"${breakeven * 100:,.0f} (if stock goes to $0)",
                "volume": int(strike_opt["volume"]),
                "open_interest": int(strike_opt["openInterest"]),
                "iv": round(strike_opt["iv"] * 100, 1),
                "rationale": f"Bearish bias — RSI {rsi:.0f}, {'below' if not price_above_sma20 else 'above'} SMA20. "
                             f"{'Earnings risk in ' + str(days_to_earnings) + 'd. ' if is_earnings_play else ''}"
                             f"Expected move: ±${expected_move:.2f} ({expected_move/price*100:.1f}%)",
                "risk_notes": "Max loss limited to premium paid."
            })

    # ──── PLAY 2: Straddle (Earnings / High Vol) ────
    if is_earnings_play or is_high_iv:
        atm_call = find_best_strike(chains, "call", expiry, price, "atm")
        atm_put = find_best_strike(chains, "put", expiry, price, "atm")
        if atm_call and atm_put:
            call_mid = (atm_call["bid"] + atm_call["ask"]) / 2 if atm_call["ask"] > 0 else atm_call["lastPrice"]
            put_mid = (atm_put["bid"] + atm_put["ask"]) / 2 if atm_put["ask"] > 0 else atm_put["lastPrice"]
            total_premium = call_mid + put_mid
            breakeven_up = atm_call["strike"] + total_premium
            breakeven_down = atm_put["strike"] - total_premium
            move_needed = (total_premium / price) * 100

            plays.append({
                "strategy": "Long Straddle",
                "emoji": "🎯",
                "direction": "Neutral (big move expected)",
                "action": f"BUY {ticker} ${atm_call['strike']:.0f} Call + BUY ${atm_put['strike']:.0f} Put",
                "expiry": expiry,
                "dte": dte,
                "strike": atm_call["strike"],
                "entry_price": round(total_premium, 2),
                "bid": None,
                "ask": None,
                "breakeven": f"${breakeven_down:.2f} / ${breakeven_up:.2f}",
                "pct_to_breakeven": round(move_needed, 1),
                "max_loss": round(total_premium * 100, 0),
                "max_gain": "Unlimited",
                "volume": int(atm_call["volume"] + atm_put["volume"]),
                "open_interest": int(atm_call["openInterest"] + atm_put["openInterest"]),
                "iv": round((atm_call["iv"] + atm_put["iv"]) / 2 * 100, 1),
                "rationale": f"{'Earnings in ' + str(days_to_earnings) + 'd' if is_earnings_play else 'High IV environment'}. "
                             f"Needs ±{move_needed:.1f}% move to profit. Expected move: ±${expected_move:.2f} ({expected_move/price*100:.1f}%). "
                             f"{'Expected move > breakeven — favorable setup.' if expected_move > total_premium else 'Expected move < breakeven — IV may be overstating.'}",
                "risk_notes": f"Max loss ${total_premium * 100:,.0f} if stock doesn't move. IV crush after earnings can destroy value even if direction is right."
            })

    # ──── PLAY 3: Strangle (cheaper earnings play) ────
    if is_earnings_play:
        otm_call = find_best_strike(chains, "call", expiry, price, "otm_near")
        otm_put = find_best_strike(chains, "put", expiry, price, "otm_near")
        if otm_call and otm_put and otm_call["strike"] != otm_put["strike"]:
            call_mid = (otm_call["bid"] + otm_call["ask"]) / 2 if otm_call["ask"] > 0 else otm_call["lastPrice"]
            put_mid = (otm_put["bid"] + otm_put["ask"]) / 2 if otm_put["ask"] > 0 else otm_put["lastPrice"]
            total_premium = call_mid + put_mid
            breakeven_up = otm_call["strike"] + total_premium
            breakeven_down = otm_put["strike"] - total_premium
            move_needed_up = ((breakeven_up / price) - 1) * 100
            move_needed_down = ((price - breakeven_down) / price) * 100

            plays.append({
                "strategy": "Long Strangle",
                "emoji": "🔀",
                "direction": "Neutral (big move, cheaper entry)",
                "action": f"BUY {ticker} ${otm_call['strike']:.0f} Call + BUY ${otm_put['strike']:.0f} Put",
                "expiry": expiry,
                "dte": dte,
                "strike": f"{otm_put['strike']:.0f}/{otm_call['strike']:.0f}",
                "entry_price": round(total_premium, 2),
                "bid": None,
                "ask": None,
                "breakeven": f"${breakeven_down:.2f} / ${breakeven_up:.2f}",
                "pct_to_breakeven": round(max(move_needed_up, move_needed_down), 1),
                "max_loss": round(total_premium * 100, 0),
                "max_gain": "Unlimited",
                "volume": int(otm_call["volume"] + otm_put["volume"]),
                "open_interest": int(otm_call["openInterest"] + otm_put["openInterest"]),
                "iv": round((otm_call["iv"] + otm_put["iv"]) / 2 * 100, 1),
                "rationale": f"Cheaper alternative to straddle for earnings in {days_to_earnings}d. "
                             f"Needs >{max(move_needed_up, move_needed_down):.1f}% move. "
                             f"Lower cost (${total_premium:.2f}) but wider breakevens.",
                "risk_notes": f"Max loss ${total_premium * 100:,.0f}. Requires larger move than straddle to profit."
            })

    # ──── PLAY 4: Bull Call Spread (defined risk directional) ────
    if bias == "bullish":
        long_call = find_best_strike(chains, "call", expiry, price, "atm")
        short_call = find_best_strike(chains, "call", expiry, price, "otm_far")
        if long_call and short_call and short_call["strike"] > long_call["strike"]:
            long_mid = (long_call["bid"] + long_call["ask"]) / 2 if long_call["ask"] > 0 else long_call["lastPrice"]
            short_mid = (short_call["bid"] + short_call["ask"]) / 2 if short_call["ask"] > 0 else short_call["lastPrice"]
            net_debit = long_mid - short_mid
            if net_debit > 0:
                spread_width = short_call["strike"] - long_call["strike"]
                max_profit = (spread_width - net_debit) * 100
                max_loss_val = net_debit * 100
                breakeven_val = long_call["strike"] + net_debit
                reward_risk = max_profit / max_loss_val if max_loss_val > 0 else 0

                plays.append({
                    "strategy": "Bull Call Spread",
                    "emoji": "📊",
                    "direction": "Bullish (defined risk)",
                    "action": f"BUY {ticker} ${long_call['strike']:.0f} Call / SELL ${short_call['strike']:.0f} Call",
                    "expiry": expiry,
                    "dte": dte,
                    "strike": f"{long_call['strike']:.0f}/{short_call['strike']:.0f}",
                    "entry_price": round(net_debit, 2),
                    "bid": None,
                    "ask": None,
                    "breakeven": round(breakeven_val, 2),
                    "pct_to_breakeven": round(((breakeven_val / price) - 1) * 100, 1),
                    "max_loss": round(max_loss_val, 0),
                    "max_gain": f"${max_profit:,.0f}",
                    "volume": int(long_call["volume"] + short_call["volume"]),
                    "open_interest": int(long_call["openInterest"] + short_call["openInterest"]),
                    "iv": round(long_call["iv"] * 100, 1),
                    "rationale": f"Defined-risk bullish play. Reward/risk: {reward_risk:.1f}:1. "
                                 f"Profits if {ticker} above ${breakeven_val:.2f} by {expiry}. "
                                 f"{'Earnings catalyst in ' + str(days_to_earnings) + 'd. ' if is_earnings_play else ''}",
                    "risk_notes": f"Max loss ${max_loss_val:,.0f}, max gain ${max_profit:,.0f}. Both legs expire worthless below ${long_call['strike']:.0f}."
                })

    # ──── PLAY 5: Bear Put Spread (defined risk bearish) ────
    if bias == "bearish":
        long_put = find_best_strike(chains, "put", expiry, price, "atm")
        short_put = find_best_strike(chains, "put", expiry, price, "otm_far")
        if long_put and short_put and long_put["strike"] > short_put["strike"]:
            long_mid = (long_put["bid"] + long_put["ask"]) / 2 if long_put["ask"] > 0 else long_put["lastPrice"]
            short_mid = (short_put["bid"] + short_put["ask"]) / 2 if short_put["ask"] > 0 else short_put["lastPrice"]
            net_debit = long_mid - short_mid
            if net_debit > 0:
                spread_width = long_put["strike"] - short_put["strike"]
                max_profit = (spread_width - net_debit) * 100
                max_loss_val = net_debit * 100
                breakeven_val = long_put["strike"] - net_debit
                reward_risk = max_profit / max_loss_val if max_loss_val > 0 else 0

                plays.append({
                    "strategy": "Bear Put Spread",
                    "emoji": "📊",
                    "direction": "Bearish (defined risk)",
                    "action": f"BUY {ticker} ${long_put['strike']:.0f} Put / SELL ${short_put['strike']:.0f} Put",
                    "expiry": expiry,
                    "dte": dte,
                    "strike": f"{long_put['strike']:.0f}/{short_put['strike']:.0f}",
                    "entry_price": round(net_debit, 2),
                    "bid": None,
                    "ask": None,
                    "breakeven": round(breakeven_val, 2),
                    "pct_to_breakeven": round(((price - breakeven_val) / price) * 100, 1),
                    "max_loss": round(max_loss_val, 0),
                    "max_gain": f"${max_profit:,.0f}",
                    "volume": int(long_put["volume"] + short_put["volume"]),
                    "open_interest": int(long_put["openInterest"] + short_put["openInterest"]),
                    "iv": round(long_put["iv"] * 100, 1),
                    "rationale": f"Defined-risk bearish play. Reward/risk: {reward_risk:.1f}:1. "
                                 f"Profits if {ticker} below ${breakeven_val:.2f} by {expiry}.",
                    "risk_notes": f"Max loss ${max_loss_val:,.0f}, max gain ${max_profit:,.0f}."
                })

    # ──── PLAY 6: Credit Spread (sell premium in high IV) ────
    if is_high_iv and not is_earnings_play:
        if bias != "bearish":
            short_put = find_best_strike(chains, "put", expiry, price, "otm_near")
            long_put = find_best_strike(chains, "put", expiry, price, "otm_far")
            if short_put and long_put and short_put["strike"] > long_put["strike"]:
                short_mid = (short_put["bid"] + short_put["ask"]) / 2 if short_put["ask"] > 0 else short_put["lastPrice"]
                long_mid = (long_put["bid"] + long_put["ask"]) / 2 if long_put["ask"] > 0 else long_put["lastPrice"]
                net_credit = short_mid - long_mid
                if net_credit > 0:
                    spread_width = short_put["strike"] - long_put["strike"]
                    max_loss_val = (spread_width - net_credit) * 100
                    max_profit = net_credit * 100
                    breakeven_val = short_put["strike"] - net_credit

                    plays.append({
                        "strategy": "Bull Put Credit Spread",
                        "emoji": "💰",
                        "direction": "Neutral-to-bullish (sell premium)",
                        "action": f"SELL {ticker} ${short_put['strike']:.0f} Put / BUY ${long_put['strike']:.0f} Put",
                        "expiry": expiry,
                        "dte": dte,
                        "strike": f"{short_put['strike']:.0f}/{long_put['strike']:.0f}",
                        "entry_price": round(net_credit, 2),
                        "bid": None,
                        "ask": None,
                        "breakeven": round(breakeven_val, 2),
                        "pct_to_breakeven": round(((price - breakeven_val) / price) * 100, 1),
                        "max_loss": round(max_loss_val, 0),
                        "max_gain": f"${max_profit:,.0f}",
                        "volume": int(short_put["volume"] + long_put["volume"]),
                        "open_interest": int(short_put["openInterest"] + long_put["openInterest"]),
                        "iv": round(short_put["iv"] * 100, 1),
                        "rationale": f"Sell elevated IV ({iv_30d:.0f}%). Collect ${net_credit:.2f} credit. "
                                     f"Profitable if {ticker} stays above ${breakeven_val:.2f}. "
                                     f"Win rate tends to be higher than directional plays.",
                        "risk_notes": f"Max loss ${max_loss_val:,.0f} if {ticker} drops below ${long_put['strike']:.0f}. Margin required."
                    })

    return plays


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

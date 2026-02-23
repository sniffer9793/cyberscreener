"""
CyberScreener API v3 — FastAPI backend with auth, v2 scoring, and self-calibration.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, BackgroundTasks, Query, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import time
import hashlib
import json

from core.scanner import (
    run_scan,
    fetch_options_chain, generate_plays, fetch_ticker_data,
    score_long_term, score_options, get_weights, set_weights,
    DEFAULT_LT_WEIGHTS, DEFAULT_OPT_WEIGHTS,
)
from core.universe import (
    CYBER_UNIVERSE, ENERGY_UNIVERSE, DEFENSE_UNIVERSE,
    get_universe_by_sector, get_sector_summary, get_all_tickers,
    ALL_CYBER_TICKERS, ALL_ENERGY_TICKERS, ALL_DEFENSE_TICKERS,
    get_ticker_meta,
)
# Full multi-sector universe (cyber + energy + defense, deduplicated)
ALL_TICKERS = sorted(list(set(ALL_CYBER_TICKERS + ALL_ENERGY_TICKERS + ALL_DEFENSE_TICKERS)))
from db.models import (
    init_db, save_scan, get_score_history,
    get_all_scores_for_backtest, get_scan_count, get_db,
    save_score_weights, get_latest_weights,
    get_watchlist, add_to_watchlist, remove_from_watchlist, get_watchlist_tickers,
)
from db.migrate_timing import run_migration as _run_timing_migration
from db.migrate_sectors import run_migration as _run_sectors_migration
from db.migrate_threat import run_migration as _run_threat_migration
from db.migrate_watchlist import run_migration as _run_watchlist_migration
from intel.earnings_calendar import seed_from_payload, save_earnings_date, get_all_upcoming_dates
from backtest.engine import (
    run_full_backtest,
    backtest_score_vs_returns,
    backtest_layer_attribution,
    backtest_earnings_timing,
    calibrate_weights,
)

API_PASSWORD = os.environ.get("CYBERSCREENER_PASSWORD", "cybershield2026")

# Allowed origins: production domain + local dev
_ALLOWED_ORIGINS = [
    "https://cyber.keltonshockey.com",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
]

app = FastAPI(title="Augur API", version="3.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key"],
    allow_credentials=False,
)

# ── Simple in-memory rate limiter ──────────────────────────────────────────────
_rate_limits: dict = {}  # key -> list of timestamps

def _check_rate_limit(key: str, max_calls: int = 10, window_seconds: int = 60) -> bool:
    """Returns True if under limit (OK to proceed). False = rate limited."""
    now = time.time()
    cutoff = now - window_seconds
    times = [t for t in _rate_limits.get(key, []) if t > cutoff]
    if len(times) >= max_calls:
        _rate_limits[key] = times
        return False
    times.append(now)
    _rate_limits[key] = times
    return True

init_db()
try:
    _run_timing_migration()
    print("✅ Timing migration complete")
except Exception as _me:
    print(f"Timing migration warning: {_me}")
try:
    _run_sectors_migration()
    print("✅ Sectors migration complete")
except Exception as _me:
    print(f"Sectors migration warning: {_me}")
try:
    _run_threat_migration()
except Exception as _me:
    print(f"Threat migration warning: {_me}")
try:
    _run_watchlist_migration()
    print("✅ Watchlist migration complete")
except Exception as _me:
    print(f"Watchlist migration warning: {_me}")

# Load saved weights if available
def _load_saved_weights():
    for score_type in ["lt", "opt"]:
        saved = get_latest_weights(score_type)
        if saved:
            if score_type == "lt":
                set_weights(lt_weights=saved["weights"])
            else:
                set_weights(opt_weights=saved["weights"])
try:
    _load_saved_weights()
except Exception:
    pass

from fastapi.responses import HTMLResponse

def _find_dashboard():
    candidates = [
        Path(__file__).parent / "dashboard_embed.html",
        Path(__file__).parent.parent / "dashboard_embed.html",
        Path("/app/dashboard_embed.html"),
        Path("/app/api/dashboard_embed.html"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    p = _find_dashboard()
    if p:
        return p.read_text()
    return f"<h1>Dashboard not found</h1>"

@app.get("/dashboard", response_class=HTMLResponse)
def serve_dashboard_alt():
    return serve_dashboard()

# ─── Auth ───
class AuthRequest(BaseModel):
    password: str

@app.post("/auth")
def authenticate(req: AuthRequest):
    if req.password == API_PASSWORD:
        token = hashlib.sha256(API_PASSWORD.encode()).hexdigest()
        return {"authenticated": True, "token": token}
    raise HTTPException(status_code=401, detail="Wrong password")

@app.get("/health")
def health():
    return {"status": "ok", "version": "3.0.0", "scans": get_scan_count()}


# ─── Backfill ───
_backfill_status = {"running": False, "message": "idle"}

@app.post("/backfill")
def trigger_backfill(background_tasks: BackgroundTasks, months: int = Query(6, ge=1, le=12)):
    if _backfill_status["running"]:
        return {"status": "busy", "message": _backfill_status["message"]}
    background_tasks.add_task(_run_backfill_background, months)
    return {"status": "started", "message": f"Backfilling {months} months of history..."}

@app.get("/backfill/status")
def backfill_status():
    return _backfill_status

def _run_backfill_background(months):
    global _backfill_status
    _backfill_status["running"] = True
    _backfill_status["message"] = "Starting backfill..."
    try:
        import yfinance as yf
        import pandas as pd
        import numpy as np
        from datetime import timedelta

        _backfill_status["message"] = f"Downloading price history for {len(ALL_TICKERS)} tickers..."
        data = yf.download(ALL_TICKERS, period="1y", group_by="ticker", progress=False, threads=True)
        if data is None or data.empty:
            _backfill_status["message"] = "Error: Failed to download data"
            _backfill_status["running"] = False
            return

        _backfill_status["message"] = "Fetching fundamentals..."
        fundamentals = {}
        for ticker in ALL_TICKERS:
            try:
                t = yf.Ticker(ticker)
                info = t.info
                fundamentals[ticker] = {
                    "market_cap": info.get("marketCap", 0),
                    "revenue": info.get("totalRevenue", 0),
                    "revenue_growth": info.get("revenueGrowth", 0),
                    "gross_margins": info.get("grossMargins", 0),
                    "operating_margins": info.get("operatingMargins", 0),
                    "fcf": info.get("freeCashflow", 0),
                    "ps_ratio": info.get("priceToSalesTrailing12Months"),
                    "pe_ratio": info.get("trailingPE"),
                    "eps": info.get("trailingEps"),
                    "beta": info.get("beta", 1.0),
                    "short_pct": info.get("shortPercentOfFloat", 0) or 0,
                    "enterprise_value": info.get("enterpriseValue", 0),
                }
                time.sleep(0.2)
            except Exception:
                fundamentals[ticker] = {}

        today = datetime.today()
        start_date = today - timedelta(days=months * 30)
        sim_dates = []
        current = start_date
        while current < today - timedelta(days=7):
            while current.weekday() != 0:
                current += timedelta(days=1)
            if current < today - timedelta(days=7):
                sim_dates.append(current)
            current += timedelta(days=7)

        _backfill_status["message"] = f"Simulating {len(sim_dates)} weekly scans..."
        conn = get_db()
        total_records = 0

        for sim_idx, sim_date in enumerate(sim_dates):
            sim_date_str = sim_date.strftime("%Y-%m-%d")
            _backfill_status["message"] = f"Scan {sim_idx+1}/{len(sim_dates)} ({sim_date_str})"

            cursor = conn.execute(
                "INSERT INTO scans (timestamp, tickers_scanned, config_json, intel_layers) VALUES (?, ?, ?, ?)",
                (sim_date.strftime("%Y-%m-%d %H:%M:%S"), 0, '{"mode":"backfill","scoring":"v2"}', "base")
            )
            scan_id = cursor.lastrowid
            tickers_in_scan = 0

            for ticker in ALL_TICKERS:
                try:
                    if ticker in data.columns.get_level_values(0):
                        ticker_hist = data[ticker].dropna(subset=["Close"])
                    else:
                        continue

                    mask = ticker_hist.index <= pd.Timestamp(sim_date)
                    td = ticker_hist[mask]
                    if td.empty or len(td) < 20:
                        continue

                    close = td["Close"]
                    price = float(close.iloc[-1])
                    sma_20 = float(close.rolling(20).mean().iloc[-1])
                    sma_50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
                    sma_200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

                    delta_c = close.diff()
                    gain = delta_c.where(delta_c > 0, 0).rolling(14).mean()
                    loss_c = (-delta_c.where(delta_c < 0, 0)).rolling(14).mean()
                    rs = gain / loss_c
                    rsi = float((100 - (100 / (1 + rs))).iloc[-1])
                    if np.isnan(rsi): rsi = 50.0

                    rolling_std = float(close.rolling(20).std().iloc[-1])
                    bb_width = (rolling_std * 4) / sma_20 * 100 if sma_20 > 0 else 0

                    vol_ratio = 1.0
                    if "Volume" in td.columns and len(td) >= 20:
                        v20 = td["Volume"].tail(20).mean()
                        v5 = td["Volume"].tail(5).mean()
                        vol_ratio = float(v5 / v20) if v20 > 0 else 1.0

                    p21 = float(close.iloc[-21]) if len(close) >= 21 else price
                    p63 = float(close.iloc[-63]) if len(close) >= 63 else price
                    p0 = float(close.iloc[0])
                    hi = float(td["High"].max()) if "High" in td.columns else price

                    fund = fundamentals.get(ticker, {})
                    mc = fund.get("market_cap", 0)
                    rev = fund.get("revenue", 0)
                    fcf = fund.get("fcf", 0)
                    ev = fund.get("enterprise_value", 0)

                    row = {
                        "ticker": ticker, "price": round(price, 2),
                        "market_cap_b": round(mc / 1e9, 1) if mc else None,
                        "revenue_b": round(rev / 1e9, 2) if rev else None,
                        "revenue_growth_pct": round(fund.get("revenue_growth", 0) * 100, 1) if fund.get("revenue_growth") else None,
                        "gross_margin_pct": round(fund.get("gross_margins", 0) * 100, 1) if fund.get("gross_margins") else None,
                        "operating_margin_pct": round(fund.get("operating_margins", 0) * 100, 1) if fund.get("operating_margins") else None,
                        "fcf_m": round(fcf / 1e6, 0) if fcf else None,
                        "fcf_margin_pct": round((fcf / rev) * 100, 1) if rev and rev > 0 and fcf else None,
                        "ps_ratio": round(fund.get("ps_ratio"), 1) if fund.get("ps_ratio") else None,
                        "pe_ratio": round(fund.get("pe_ratio"), 1) if fund.get("pe_ratio") else None,
                        "ev_revenue": round(ev / rev, 1) if ev and rev and rev > 0 else None,
                        "eps": fund.get("eps"),
                        "beta": round(fund.get("beta", 1.0), 2) if fund.get("beta") else None,
                        "short_pct": round(fund.get("short_pct", 0) * 100, 1),
                        "rsi": round(rsi, 1), "sma_20": round(sma_20, 2),
                        "sma_50": round(sma_50, 2) if sma_50 else None,
                        "sma_200": round(sma_200, 2) if sma_200 else None,
                        "bb_width": round(bb_width, 1), "vol_ratio": round(vol_ratio, 2),
                        "perf_3m": round(((price / p63) - 1) * 100, 1),
                        "perf_1m": round(((price / p21) - 1) * 100, 1),
                        "perf_1y": round(((price / p0) - 1) * 100, 1),
                        "pct_from_52w_high": round(((price / hi) - 1) * 100, 1),
                        "iv_30d": None, "iv_rank": None, "days_to_earnings": None,
                        "price_above_sma20": price > sma_20,
                        "price_above_sma50": price > sma_50 if sma_50 else None,
                        "price_above_sma200": price > sma_200 if sma_200 else None,
                    }

                    lt_score, _, lt_bd = score_long_term(row)
                    opt_score, _, opt_bd = score_options(row)

                    conn.execute("""
                        INSERT INTO scores (
                            scan_id, ticker, price, market_cap_b, lt_score, opt_score,
                            lt_rule_of_40, lt_valuation, lt_fcf_margin, lt_trend, lt_earnings_quality, lt_discount_momentum,
                            opt_earnings_catalyst, opt_iv_context, opt_directional, opt_technical, opt_liquidity, opt_asymmetry,
                            revenue_growth_pct, gross_margin_pct, operating_margin_pct,
                            ps_ratio, pe_ratio, ev_revenue, fcf_m, fcf_margin_pct, revenue_b,
                            rsi, sma_20, sma_50, sma_200, bb_width, vol_ratio, iv_30d, iv_rank, beta, short_pct,
                            perf_1y, perf_3m, perf_1m, pct_from_52w_high, days_to_earnings,
                            sec_score, sentiment_score, whale_score,
                            lt_breakdown, opt_breakdown
                        ) VALUES (
                            ?,?,?,?,?,?,
                            ?,?,?,?,?,?,
                            ?,?,?,?,?,?,
                            ?,?,?,
                            ?,?,?,?,?,?,
                            ?,?,?,?,?,?,?,?,?,?,
                            ?,?,?,?,?,
                            ?,?,?,
                            ?,?
                        )
                    """, (
                        scan_id, ticker, row["price"], row.get("market_cap_b"), lt_score, opt_score,
                        lt_bd.get("rule_of_40", {}).get("points", 0), lt_bd.get("valuation", {}).get("points", 0),
                        lt_bd.get("fcf_margin", {}).get("points", 0), lt_bd.get("trend", {}).get("points", 0),
                        lt_bd.get("earnings_quality", {}).get("points", 0), lt_bd.get("discount_momentum", {}).get("points", 0),
                        opt_bd.get("earnings_catalyst", {}).get("points", 0), opt_bd.get("iv_context", {}).get("points", 0),
                        opt_bd.get("directional", {}).get("points", 0), opt_bd.get("technical", {}).get("points", 0),
                        opt_bd.get("liquidity", {}).get("points", 0), opt_bd.get("asymmetry", {}).get("points", 0),
                        row.get("revenue_growth_pct"), row.get("gross_margin_pct"), row.get("operating_margin_pct"),
                        row.get("ps_ratio"), row.get("pe_ratio"), row.get("ev_revenue"),
                        row.get("fcf_m"), row.get("fcf_margin_pct"), row.get("revenue_b"),
                        row["rsi"], row["sma_20"], row.get("sma_50"), row.get("sma_200"),
                        row["bb_width"], row["vol_ratio"], None, None, row.get("beta"), row.get("short_pct"),
                        row["perf_1y"], row["perf_3m"], row.get("perf_1m"), row["pct_from_52w_high"], None,
                        0, 0, 0,
                        json.dumps(lt_bd), json.dumps(opt_bd),
                    ))

                    conn.execute("INSERT OR IGNORE INTO prices (ticker, date, close_price) VALUES (?, ?, ?)",
                                 (ticker, sim_date_str, row["price"]))
                    for fwd in [7, 14, 30, 60]:
                        fmask = ticker_hist.index > pd.Timestamp(sim_date)
                        future = ticker_hist[fmask]
                        if not future.empty and len(future) >= fwd:
                            fp = float(future["Close"].iloc[min(fwd, len(future)-1)])
                            fd = (sim_date + timedelta(days=fwd)).strftime("%Y-%m-%d")
                            conn.execute("INSERT OR IGNORE INTO prices (ticker, date, close_price) VALUES (?, ?, ?)",
                                         (ticker, fd, fp))

                    tickers_in_scan += 1
                    total_records += 1
                except Exception:
                    continue

            conn.execute("UPDATE scans SET tickers_scanned = ? WHERE id = ?", (tickers_in_scan, scan_id))
            conn.commit()

        conn.close()
        _backfill_status["message"] = f"✅ Complete! {len(sim_dates)} scans, {total_records} records"
    except Exception as e:
        _backfill_status["message"] = f"Error: {str(e)}"
    finally:
        _backfill_status["running"] = False


# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

class ScanRequest(BaseModel):
    tickers: Optional[list[str]] = None
    enable_sec: bool = True
    enable_sentiment: bool = False
    enable_whale: bool = False

class ScanStatus(BaseModel):
    status: str
    scan_id: Optional[int] = None
    tickers_scanned: int = 0
    duration_seconds: Optional[float] = None
    message: str = ""

_scan_status = {"running": False, "last_scan_id": None, "message": ""}


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/api/info")
def api_info():
    return {
        "service": "Augur",
        "version": "3.1.0",
        "scoring": "v2",
        "total_scans": get_scan_count(),
        "active_weights": get_weights(),
    }

@app.get("/tickers")
def get_tickers():
    return {"universe": CYBER_UNIVERSE, "all_tickers": ALL_TICKERS, "total": len(ALL_TICKERS)}

@app.post("/scan", response_model=ScanStatus)
def trigger_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    if not _check_rate_limit("scan", max_calls=5, window_seconds=300):
        raise HTTPException(status_code=429, detail="Too many scan requests. Try again in 5 minutes.")
    if _scan_status["running"]:
        return ScanStatus(status="busy", message="A scan is already running.")
    background_tasks.add_task(_run_scan_background, req)
    return ScanStatus(status="started", message="Scan started. Check /scan/status.")

def _run_scan_background(req: ScanRequest):
    global _scan_status
    _scan_status["running"] = True
    _scan_status["message"] = "Scanning..."
    start_time = time.time()
    # Merge standard universe with watchlist tickers
    try:
        wl_tickers = get_watchlist_tickers()
    except Exception:
        wl_tickers = []
    base_tickers = req.tickers or ALL_TICKERS
    tickers = sorted(set(base_tickers) | set(wl_tickers))
    try:
        def progress_callback(ticker, i, total):
            _scan_status["message"] = f"Scanning {ticker} ({i+1}/{total})"
        results = run_scan(tickers=tickers, enable_sec=req.enable_sec, callback=progress_callback)
        duration = time.time() - start_time
        intel_layers = []
        if req.enable_sec: intel_layers.append("sec")
        if req.enable_sentiment: intel_layers.append("sentiment")
        if req.enable_whale: intel_layers.append("whale")
        scan_id = save_scan(results, intel_layers=intel_layers, duration_seconds=duration)
        _scan_status["last_scan_id"] = scan_id
        _scan_status["message"] = f"Complete. {len(results)} tickers in {duration:.1f}s."
    except Exception as e:
        _scan_status["message"] = f"Error: {str(e)}"
    finally:
        _scan_status["running"] = False

@app.get("/scan/status")
def scan_status():
    return _scan_status

@app.get("/scores/latest")
def get_latest_scores(limit: int = Query(100, ge=1, le=200)):
    """
    Return the most recent score for each ticker across all scans.
    Uses a per-ticker max(scan_id) join so partial scans (e.g. 5-ticker
    test runs) don't erase older data for tickers not in that scan.
    """
    conn = get_db()
    scan = conn.execute("SELECT id, timestamp FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not scan:
        conn.close()
        return {"message": "No scans found.", "results": []}
    rows = conn.execute("""
        SELECT s.*
        FROM scores s
        INNER JOIN (
            SELECT ticker, MAX(scan_id) AS max_scan_id
            FROM scores
            GROUP BY ticker
        ) latest ON s.ticker = latest.ticker AND s.scan_id = latest.max_scan_id
        ORDER BY s.lt_score DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return {"scan_id": scan["id"], "scan_timestamp": scan["timestamp"], "results": [dict(r) for r in rows]}

@app.get("/scores/{ticker}")
def get_ticker_scores(ticker: str, days: int = Query(90, ge=7, le=365)):
    history = get_score_history(ticker.upper(), days)
    if not history:
        return {"ticker": ticker.upper(), "history": [], "message": "No data found."}
    return {"ticker": ticker.upper(), "history": history, "data_points": len(history)}


@app.get("/chart/{ticker}")
def get_chart_data(ticker: str, days: int = Query(90, ge=30, le=365)):
    """Price history with computed SMA/RSI and detected signal overlays for charting."""
    from datetime import timedelta

    t = ticker.upper()
    conn = get_db()

    # Fetch extra history for SMA-200 warmup
    fetch_days = max(days + 220, 365)
    cutoff_all = (datetime.now() - timedelta(days=fetch_days)).strftime("%Y-%m-%d")
    display_cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    rows = conn.execute(
        "SELECT date, close_price FROM prices WHERE ticker = ? AND date >= ? ORDER BY date ASC",
        (t, cutoff_all)
    ).fetchall()

    if not rows:
        conn.close()
        return {"ticker": t, "prices": [], "signals": []}

    dates = [r["date"] for r in rows]
    closes = [r["close_price"] for r in rows]
    n = len(closes)

    def sma_series(closes, period):
        out = [None] * len(closes)
        for i in range(period - 1, len(closes)):
            out[i] = sum(closes[i - period + 1:i + 1]) / period
        return out

    def rsi_series(closes, period=14):
        out = [None] * len(closes)
        if len(closes) < period + 1:
            return out
        gains, losses = [], []
        for i in range(1, period + 1):
            d = closes[i] - closes[i - 1]
            gains.append(max(d, 0))
            losses.append(max(-d, 0))
        avg_g = sum(gains) / period
        avg_l = sum(losses) / period
        out[period] = 100.0 if avg_l == 0 else round(100 - 100 / (1 + avg_g / avg_l), 1)
        for i in range(period + 1, len(closes)):
            d = closes[i] - closes[i - 1]
            avg_g = (avg_g * (period - 1) + max(d, 0)) / period
            avg_l = (avg_l * (period - 1) + max(-d, 0)) / period
            out[i] = 100.0 if avg_l == 0 else round(100 - 100 / (1 + avg_g / avg_l), 1)
        return out

    sma20 = sma_series(closes, 20)
    sma50 = sma_series(closes, 50)
    sma200 = sma_series(closes, 200)
    rsi_vals = rsi_series(closes)

    prices_out = []
    for i in range(n):
        if dates[i] >= display_cutoff:
            prices_out.append({
                "date": dates[i],
                "close": round(closes[i], 2),
                "sma20": round(sma20[i], 2) if sma20[i] is not None else None,
                "sma50": round(sma50[i], 2) if sma50[i] is not None else None,
                "sma200": round(sma200[i], 2) if sma200[i] is not None else None,
                "rsi": rsi_vals[i],
            })

    signals = []

    # RSI extreme crossings
    for i in range(1, n):
        if dates[i] < display_cutoff:
            continue
        pr, cr = rsi_vals[i - 1], rsi_vals[i]
        if pr is not None and cr is not None:
            if pr > 30 and cr <= 30:
                signals.append({"date": dates[i], "type": "rsi_oversold", "label": f"RSI {cr:.0f} OS"})
            elif pr < 70 and cr >= 70:
                signals.append({"date": dates[i], "type": "rsi_overbought", "label": f"RSI {cr:.0f} OB"})

    # SMA 20/50 crossovers
    for i in range(1, n):
        if dates[i] < display_cutoff:
            continue
        ps20, ps50, cs20, cs50 = sma20[i - 1], sma50[i - 1], sma20[i], sma50[i]
        if all(x is not None for x in [ps20, ps50, cs20, cs50]):
            if ps20 < ps50 and cs20 >= cs50:
                signals.append({"date": dates[i], "type": "sma_cross_bull", "label": "20/50 ↑"})
            elif ps20 > ps50 and cs20 <= cs50:
                signals.append({"date": dates[i], "type": "sma_cross_bear", "label": "20/50 ↓"})

    # Insider signals from scores table (detect increases in buy/sell counts)
    try:
        insider_rows = conn.execute("""
            SELECT sc.timestamp, s.insider_buys_30d, s.insider_sells_30d
            FROM scores s JOIN scans sc ON s.scan_id = sc.id
            WHERE s.ticker = ? AND sc.timestamp >= ?
            ORDER BY sc.timestamp ASC
        """, (t, display_cutoff)).fetchall()
        prev_b, prev_s = 0, 0
        for row in insider_rows:
            d = row["timestamp"][:10]
            b = row["insider_buys_30d"] or 0
            s = row["insider_sells_30d"] or 0
            if b > prev_b:
                signals.append({"date": d, "type": "insider_buy", "label": "Insider Buy"})
            if s > prev_s:
                signals.append({"date": d, "type": "insider_sell", "label": "Insider Sell"})
            prev_b, prev_s = b, s
    except Exception:
        pass

    # Earnings dates from DB
    try:
        earn_rows = conn.execute(
            "SELECT earnings_date FROM earnings_dates WHERE ticker = ? ORDER BY earnings_date ASC",
            (t,)
        ).fetchall()
        for row in earn_rows:
            ed = row[0] if not isinstance(row, dict) else row["earnings_date"]
            if ed and ed >= display_cutoff:
                signals.append({"date": ed, "type": "earnings", "label": "Earnings"})
    except Exception:
        pass

    # Approximate earnings from scores (days_to_earnings near 0)
    try:
        earn_scan_rows = conn.execute("""
            SELECT sc.timestamp FROM scores s
            JOIN scans sc ON s.scan_id = sc.id
            WHERE s.ticker = ? AND s.days_to_earnings IS NOT NULL
              AND s.days_to_earnings <= 2 AND sc.timestamp >= ?
            ORDER BY sc.timestamp ASC
        """, (t, display_cutoff)).fetchall()
        seen = set()
        for row in earn_scan_rows:
            d = row["timestamp"][:10]
            if d not in seen:
                seen.add(d)
                # Don't duplicate if already have an earnings signal within 7 days
                too_close = any(
                    s_["type"] == "earnings" and
                    abs((datetime.strptime(s_["date"], "%Y-%m-%d") - datetime.strptime(d, "%Y-%m-%d")).days) < 7
                    for s_ in signals
                )
                if not too_close:
                    signals.append({"date": d, "type": "earnings", "label": "Earnings ~"})
    except Exception:
        pass

    conn.close()
    signals.sort(key=lambda s: s["date"])
    return {"ticker": t, "prices": prices_out, "signals": signals}


# ─── Backtest ───

@app.get("/backtest")
def run_backtest_all(days: int = Query(180, ge=30, le=365), forward_period: int = Query(30, ge=7, le=90)):
    return run_full_backtest(days, forward_period)

@app.get("/backtest/score-vs-returns")
def backtest_scores(days: int = Query(180, ge=30, le=365), forward_period: int = Query(30, ge=7, le=90)):
    return backtest_score_vs_returns(days, forward_period)

@app.get("/backtest/layer-attribution")
def backtest_layers(days: int = Query(180, ge=30, le=365), forward_period: int = Query(30, ge=7, le=90)):
    return backtest_layer_attribution(days, forward_period)

@app.get("/backtest/earnings-timing")
def backtest_earnings(days: int = Query(180, ge=30, le=365)):
    return backtest_earnings_timing(days)


# ─── Self-Calibration ───

@app.post("/calibrate")
def trigger_calibration(
    days: int = Query(180, ge=30, le=365),
    forward_period: int = Query(30, ge=7, le=90),
    dry_run: bool = Query(False),
):
    """Auto-adjust scoring weights based on backtest data."""
    return calibrate_weights(days, forward_period, dry_run=dry_run)

@app.get("/weights")
def get_current_weights():
    """Get current scoring weights and calibration history."""
    current = get_weights()
    lt_saved = get_latest_weights("lt")
    opt_saved = get_latest_weights("opt")
    return {
        "active_weights": current,
        "defaults": {"lt": DEFAULT_LT_WEIGHTS, "opt": DEFAULT_OPT_WEIGHTS},
        "last_calibration": {
            "lt": {
                "timestamp": lt_saved.get("timestamp") if lt_saved else None,
                "correlation": lt_saved.get("backtest_correlation") if lt_saved else None,
                "quintile_spread": lt_saved.get("backtest_quintile_spread") if lt_saved else None,
            } if lt_saved else None,
            "opt": {
                "timestamp": opt_saved.get("timestamp") if opt_saved else None,
            } if opt_saved else None,
        }
    }

@app.post("/weights/reset")
def reset_weights():
    """Reset weights to defaults."""
    set_weights(lt_weights=DEFAULT_LT_WEIGHTS, opt_weights=DEFAULT_OPT_WEIGHTS)
    return {"status": "reset", "weights": get_weights()}


# ─── Options Play Builder ───

_plays_cache = {}
_plays_status = {}

def _fetch_plays_background(ticker):
    global _plays_status, _plays_cache
    _plays_status[ticker] = {"running": True, "message": f"Fetching data for {ticker}..."}
    try:
        data = fetch_ticker_data(ticker)
        if not data:
            _plays_status[ticker] = {"running": False, "message": "done",
                                     "result": {"ticker": ticker, "plays": [], "error": "Could not fetch data"}}
            return

        _plays_status[ticker]["message"] = f"Fetching options chain for {ticker}..."
        chains = fetch_options_chain(ticker)
        if not chains:
            _plays_status[ticker] = {"running": False, "message": "done",
                                     "result": {"ticker": ticker, "plays": [], "price": data.get("price"),
                                                "error": "No options chain available"}}
            return

        _plays_status[ticker]["message"] = f"Generating plays for {ticker}..."
        plays = generate_plays(
            ticker=ticker, price=data["price"], chains=chains,
            days_to_earnings=data.get("days_to_earnings"),
            rsi=data.get("rsi", 50), iv_30d=data.get("iv_30d"),
            price_above_sma20=data.get("price_above_sma20", True),
            price_above_sma50=data.get("price_above_sma50", True),
            perf_3m=data.get("perf_3m", 0),
        )

        result = {
            "ticker": ticker, "price": data["price"],
            "rsi": data.get("rsi"), "iv_30d": data.get("iv_30d"),
            "iv_rank": data.get("iv_rank"),
            "days_to_earnings": data.get("days_to_earnings"),
            "beta": data.get("beta"), "perf_3m": data.get("perf_3m"),
            "bb_width": data.get("bb_width"), "vol_ratio": data.get("vol_ratio"),
            "pct_from_52w_high": data.get("pct_from_52w_high"),
            "plays": plays, "play_count": len(plays),
            "timestamp": datetime.now().isoformat(),
        }
        _plays_cache[ticker] = {"data": result, "timestamp": datetime.now().isoformat()}
        _plays_status[ticker] = {"running": False, "message": "done", "result": result}
    except Exception as e:
        _plays_status[ticker] = {"running": False, "message": "done",
                                 "result": {"ticker": ticker, "plays": [], "error": str(e)}}


@app.get("/plays/top/recommendations")
def get_top_plays(limit: int = Query(5, ge=1, le=15)):
    conn = get_db()
    scan = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not scan:
        conn.close()
        return {"plays": [], "message": "No scans found."}

    rows = conn.execute("""
        SELECT ticker, price, opt_score, lt_score, rsi, iv_30d, days_to_earnings,
               bb_width, vol_ratio, beta, perf_3m, pct_from_52w_high
        FROM scores WHERE scan_id = ? ORDER BY opt_score DESC LIMIT ?
    """, (scan["id"], limit)).fetchall()
    conn.close()

    results = []
    for row in rows:
        row = dict(row)
        ticker = row["ticker"]
        try:
            chains = fetch_options_chain(ticker)
            if not chains:
                results.append({"ticker": ticker, "opt_score": row["opt_score"], "plays": [], "error": "No options chain"})
                continue
            plays = generate_plays(
                ticker=ticker, price=row["price"], chains=chains,
                days_to_earnings=row.get("days_to_earnings"),
                rsi=row.get("rsi", 50), iv_30d=row.get("iv_30d"),
                price_above_sma20=True, price_above_sma50=True,
                perf_3m=row.get("perf_3m", 0),
            )
            results.append({
                "ticker": ticker, "opt_score": row["opt_score"], "lt_score": row["lt_score"],
                "price": row["price"], "plays": plays, "play_count": len(plays),
            })
            time.sleep(0.3)
        except Exception as e:
            results.append({"ticker": ticker, "opt_score": row["opt_score"], "plays": [], "error": str(e)})

    return {"results": results, "total_plays": sum(r.get("play_count", 0) for r in results), "timestamp": datetime.now().isoformat()}


@app.post("/plays/{ticker}/generate")
def trigger_plays(ticker: str, background_tasks: BackgroundTasks):
    ticker = ticker.upper()
    if ticker not in ALL_TICKERS:
        raise HTTPException(status_code=404, detail=f"{ticker} not in universe")

    if ticker in _plays_cache:
        cached = _plays_cache[ticker]
        try:
            age = (datetime.now() - datetime.fromisoformat(cached["timestamp"])).seconds
            if age < 300:
                return {"status": "cached", "result": cached["data"]}
        except Exception:
            pass

    if ticker in _plays_status and _plays_status[ticker].get("running"):
        return {"status": "running", "message": _plays_status[ticker].get("message", "Working...")}

    background_tasks.add_task(_fetch_plays_background, ticker)
    return {"status": "started", "message": f"Generating plays for {ticker}..."}


@app.get("/plays/{ticker}/status")
def plays_status(ticker: str):
    ticker = ticker.upper()
    st = _plays_status.get(ticker)
    if not st:
        return {"status": "not_started"}
    if st["running"]:
        return {"status": "running", "message": st.get("message", "Working...")}
    return {"status": "done", "result": st.get("result")}


@app.get("/plays/{ticker}")
def get_plays_for_ticker(ticker: str):
    ticker = ticker.upper()
    if ticker not in ALL_TICKERS:
        raise HTTPException(status_code=404, detail=f"{ticker} not in universe")

    if ticker in _plays_cache:
        return _plays_cache[ticker]["data"]

    st = _plays_status.get(ticker)
    if st and not st.get("running") and st.get("result"):
        return st["result"]

    # Sync fallback
    try:
        data = fetch_ticker_data(ticker)
        if not data:
            return {"ticker": ticker, "plays": [], "error": "Could not fetch data"}
        chains = fetch_options_chain(ticker)
        if not chains:
            return {"ticker": ticker, "plays": [], "error": "No options chain", "price": data.get("price")}
        plays = generate_plays(
            ticker=ticker, price=data["price"], chains=chains,
            days_to_earnings=data.get("days_to_earnings"),
            rsi=data.get("rsi", 50), iv_30d=data.get("iv_30d"),
            price_above_sma20=data.get("price_above_sma20", True),
            price_above_sma50=data.get("price_above_sma50", True),
            perf_3m=data.get("perf_3m", 0),
        )
        return {"ticker": ticker, "price": data["price"], "plays": plays, "play_count": len(plays)}
    except Exception as e:
        return {"ticker": ticker, "plays": [], "error": str(e)}



# ─── Timing Debug Endpoints ───

@app.get("/debug/timing/{ticker}")
def debug_timing(ticker: str):
    """
    Test timing intelligence for a single ticker without running a full scan.
    Shows horizon classification, expiry selection, and all inputs used.
    """
    import yfinance as yf
    from core.timing import compute_timing_intelligence, get_earnings_date, classify_horizon
    import math

    def _safe(v, d=0.0):
        if v is None: return d
        try:
            f = float(v)
            return d if math.isnan(f) else f
        except: return d

    t = yf.Ticker(ticker.upper())
    result = {"ticker": ticker.upper(), "steps": [], "timing": None, "error": None}

    try:
        # Step 1: basic data
        info = t.fast_info
        price = _safe(getattr(info, 'last_price', None), 0)
        result["steps"].append(f"price=${price:.2f}")

        # Step 2: earnings date
        days_to_earnings = None
        try:
            ed_df = t.get_earnings_dates(limit=4)
            import pandas as pd
            if ed_df is not None and not ed_df.empty:
                now = pd.Timestamp.now(tz=ed_df.index[0].tzinfo) if ed_df.index[0].tzinfo else pd.Timestamp.now()
                future = ed_df[ed_df.index >= now]
                if not future.empty:
                    ed = future.index[0].date()
                    from datetime import datetime
                    days_to_earnings = (ed - datetime.today().date()).days
        except Exception as e:
            result["steps"].append(f"yfinance earnings date failed: {e}")

        dte_final, earnings_source = get_earnings_date(ticker.upper(), days_to_earnings)
        result["steps"].append(f"earnings_date: {dte_final}d out (source: {earnings_source})")

        # Step 3: fetch options chains
        fetched_chains = []
        try:
            dates = list(t.options) if t.options else []
            for exp in dates[:3]:
                try:
                    chain = t.option_chain(exp)
                    fetched_chains.append((exp, chain))
                except Exception:
                    continue
            result["steps"].append(f"chains_fetched: {len(fetched_chains)} expiries")
        except Exception as e:
            result["steps"].append(f"options fetch failed: {e}")

        # Step 4: build minimal data dict
        data = {
            "price": price,
            "days_to_earnings": dte_final,
            "lt_score": 55.0,   # placeholder — full scan needed for real value
            "opt_score": 30.0,
            "rsi": 50.0,
            "iv_rank": None,
            "whale_bias": "neutral",
            "perf_3m": 0.0,
            "iv_30d": None,
        }

        # Step 5: run timing
        timing = compute_timing_intelligence(ticker.upper(), data, fetched_chains)
        result["timing"] = timing
        result["note"] = "lt_score/opt_score are placeholders (55/30) — run /scan for real values"

    except Exception as e:
        result["error"] = str(e)

    return result


@app.get("/debug/timing-full/{ticker}")
def debug_timing_full(ticker: str):
    """
    Run a single-ticker full scan and return timing intelligence alongside all scores.
    Slower (~10s) but shows real lt_score/opt_score feeding into timing.
    """
    from core.scanner import fetch_ticker_data, score_long_term, score_options
    from core.timing import compute_timing_intelligence

    data = fetch_ticker_data(ticker.upper())
    if not data:
        return {"error": f"Failed to fetch data for {ticker}"}

    lt_score, _, lt_breakdown = score_long_term(data)
    opt_score, _, opt_breakdown = score_options(data)
    data["lt_score"] = lt_score
    data["opt_score"] = opt_score

    fetched_chains = data.pop("_fetched_chains", [])
    data.pop("_ticker_obj", None)

    timing = compute_timing_intelligence(ticker.upper(), data, fetched_chains)

    return {
        "ticker": ticker.upper(),
        "lt_score": lt_score,
        "opt_score": opt_score,
        "whale_score": data.get("whale_score", 0),
        "days_to_earnings": data.get("days_to_earnings"),
        "iv_rank": data.get("iv_rank"),
        "rsi": data.get("rsi"),
        "perf_3m": data.get("perf_3m"),
        "timing": timing,
    }

# ─── Universe Endpoints ───

@app.get("/universe")
def get_full_universe():
    return {
        "sectors": get_universe_by_sector(),
        "summary": get_sector_summary(),
        "tickers": {
            "cyber": ALL_CYBER_TICKERS,
            "energy": ALL_ENERGY_TICKERS,
            "defense": ALL_DEFENSE_TICKERS,
            "all": ALL_TICKERS,
        }
    }

@app.get("/tickers/{sector}")
def get_tickers_by_sector(sector: str):
    valid = ["cyber", "energy", "defense"]
    if sector not in valid:
        raise HTTPException(status_code=400, detail=f"Sector must be one of {valid}")
    tickers = get_all_tickers([sector])
    return {"sector": sector, "tickers": tickers, "total": len(tickers)}


# ─── Earnings Calendar Endpoints ───

class EarningsSeedRequest(BaseModel):
    dates: dict
    password: str

class EarningsSetRequest(BaseModel):
    ticker: str
    date: str
    report_time: Optional[str] = "unknown"
    password: str

@app.post("/earnings/seed")
def earnings_seed(req: EarningsSeedRequest):
    if req.password != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    return seed_from_payload(req.dates)

@app.post("/earnings/set")
def earnings_set(req: EarningsSetRequest):
    if req.password != API_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    try:
        d = datetime.strptime(req.date[:10], "%Y-%m-%d").date()
        ok = save_earnings_date(req.ticker.upper(), d, source="manual_override", report_time=req.report_time)
        if ok:
            return {"status": "saved", "ticker": req.ticker.upper(), "date": req.date}
        raise HTTPException(status_code=500, detail="Failed to save")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {req.date}")

@app.get("/earnings/upcoming")
def earnings_upcoming():
    return {"dates": get_all_upcoming_dates()}


@app.get("/weights/history")
def get_weights_history(limit: int = Query(50, ge=1, le=200)):
    """Return full calibration history from score_weights table."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM score_weights ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    history = []
    for r in rows:
        entry = dict(r)
        try:
            entry["weights"] = json.loads(entry.get("weights_json") or "{}")
        except Exception:
            entry["weights"] = {}
        history.append(entry)
    return {"history": history, "count": len(history)}


@app.get("/stats")
def get_stats():
    conn = get_db()
    stats = {}
    stats["total_scans"] = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
    stats["total_score_records"] = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
    try:
        stats["total_signals"] = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    except Exception:
        stats["total_signals"] = 0
    stats["total_price_snapshots"] = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    stats["unique_tickers_tracked"] = conn.execute("SELECT COUNT(DISTINCT ticker) FROM scores").fetchone()[0]
    stats["first_scan"] = conn.execute("SELECT MIN(timestamp) FROM scans").fetchone()[0]
    stats["last_scan"] = conn.execute("SELECT MAX(timestamp) FROM scans").fetchone()[0]
    stats["scoring_version"] = "v2"
    stats["active_weights"] = get_weights()

    latest = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if latest:
        top_lt = conn.execute("SELECT ticker, lt_score, opt_score FROM scores WHERE scan_id = ? ORDER BY lt_score DESC LIMIT 5", (latest[0],)).fetchall()
        stats["top_lt_scores"] = [{"ticker": r[0], "lt_score": r[1], "opt_score": r[2]} for r in top_lt]
        top_opt = conn.execute("SELECT ticker, opt_score, lt_score FROM scores WHERE scan_id = ? ORDER BY opt_score DESC LIMIT 5", (latest[0],)).fetchall()
        stats["top_opt_scores"] = [{"ticker": r[0], "opt_score": r[1], "lt_score": r[2]} for r in top_opt]

    conn.close()
    return stats


# ── Global Market Indices ──────────────────────────────────────────────────────

import yfinance as yf

_market_cache = {"data": None, "ts": 0}

INDICES = [
    ("^GSPC",    "S&P 500",   "NYSE",    "🇺🇸"),
    ("^IXIC",    "NASDAQ",    "NASDAQ",  "🇺🇸"),
    ("^DJI",     "Dow Jones", "NYSE",    "🇺🇸"),
    ("^GDAXI",   "DAX",       "XETRA",   "🇩🇪"),
    ("^FTSE",    "FTSE 100",  "LSE",     "🇬🇧"),
    ("^N225",    "Nikkei",    "TSE",     "🇯🇵"),
    ("^HSI",     "Hang Seng", "HKEX",    "🇭🇰"),
    ("^FCHI",    "CAC 40",    "EURONEXT","🇫🇷"),
    ("^STOXX50E","STOXX 50",  "EURONEXT","🇪🇺"),
]

# Exchange hours in UTC (open_h, open_m, close_h, close_m)
EXCHANGE_HOURS = {
    "NYSE":     (14, 30, 21,  0),
    "NASDAQ":   (14, 30, 21,  0),
    "LSE":      ( 8,  0, 16, 30),
    "XETRA":    ( 8,  0, 16, 30),
    "TSE":      ( 0,  0,  6,  0),
    "HKEX":     ( 1, 30,  8,  0),
    "EURONEXT": ( 8,  0, 16, 30),
}

def _exchange_is_open(exchange: str) -> bool:
    now = datetime.utcnow()
    # Skip weekends
    if now.weekday() >= 5:
        return False
    hrs = EXCHANGE_HOURS.get(exchange)
    if not hrs:
        return False
    oh, om, ch, cm = hrs
    open_mins  = oh * 60 + om
    close_mins = ch * 60 + cm
    now_mins   = now.hour * 60 + now.minute
    return open_mins <= now_mins < close_mins


@app.get("/market/indices")
def market_indices():
    global _market_cache
    if _market_cache["data"] and (time.time() - _market_cache["ts"]) < 300:
        return _market_cache["data"]

    results = []
    for symbol, name, exchange, flag in INDICES:
        try:
            t = yf.Ticker(symbol)
            fi = t.fast_info
            # fast_info is a FastInfo object — use getattr, not .get()
            price = (getattr(fi, "last_price", None) or
                     getattr(fi, "regular_market_price", None))
            prev_close = (getattr(fi, "previous_close", None) or
                          getattr(fi, "regular_market_previous_close", None))
            if price is None:
                # Fallback: last row of 2-day history
                hist = t.history(period="2d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
                    if len(hist) >= 2:
                        prev_close = float(hist["Close"].iloc[-2])
            price      = float(price) if price is not None else None
            prev_close = float(prev_close) if prev_close is not None else price
            change_pct = ((price - prev_close) / prev_close * 100) if (price and prev_close) else 0.0
            results.append({
                "symbol":     symbol,
                "name":       name,
                "flag":       flag,
                "exchange":   exchange,
                "price":      round(price, 2) if price is not None else None,
                "change_pct": round(change_pct, 2),
                "is_open":    _exchange_is_open(exchange),
            })
        except Exception as e:
            results.append({
                "symbol":   symbol,
                "name":     name,
                "flag":     flag,
                "exchange": exchange,
                "price":    None,
                "change_pct": None,
                "is_open":  _exchange_is_open(exchange),
                "error":    str(e),
            })

    _market_cache["data"] = results
    _market_cache["ts"]   = time.time()
    return results


# ── Intel: Cyber News + Outages ────────────────────────────────────────────────

import requests as _requests
import xml.etree.ElementTree as _ET
from concurrent.futures import ThreadPoolExecutor as _TPE

_news_cache   = {"data": None, "ts": 0}
_outage_cache = {"data": None, "ts": 0}

NEWS_SOURCES = [
    ("Bleeping Computer", "https://www.bleepingcomputer.com/feed/"),
    ("Krebs on Security", "https://krebsonsecurity.com/feed/"),
    ("Dark Reading",      "https://www.darkreading.com/rss.xml"),
]

NEWS_KEYWORDS = [
    "breach", "ransomware", "hack", "exploit", "zero-day", "vulnerability",
    "attack", "phishing", "malware", "outage", "leak", "credential",
]

STATUS_PAGES = {
    "CRWD": ("CrowdStrike",     "https://status.crowdstrike.com/api/v2/summary.json"),
    "NET":  ("Cloudflare",      "https://www.cloudflarestatus.com/api/v2/summary.json"),
    "OKTA": ("Okta",            "https://status.okta.com/api/v2/summary.json"),
    "DDOG": ("Datadog",         "https://status.datadoghq.com/api/v2/summary.json"),
    "PANW": ("Palo Alto",       "https://status.paloaltonetworks.com/api/v2/summary.json"),
    "ZS":   ("Zscaler",         "https://trust.zscaler.com/api/v2/summary.json"),
    "S":    ("SentinelOne",     "https://status.sentinelone.com/api/v2/summary.json"),
    "MSFT": ("Microsoft Azure", "https://azure.status.microsoft.com/en-us/status"),
    "GOOGL":("Google Cloud",    "https://status.cloud.google.com/"),
}

# Use full ticker list for mention detection
_ALL_TICKER_SET = set(ALL_TICKERS)


def _fetch_rss(source_name: str, url: str) -> list:
    items = []
    try:
        resp = _requests.get(url, timeout=8, headers={"User-Agent": "CyberScreener/1.0"})
        root = _ET.fromstring(resp.content)
        ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
        channel = root.find("channel") or root
        for item in channel.findall("item")[:20]:
            title   = (item.findtext("title") or "").strip()
            desc    = (item.findtext("description") or "").strip()
            link    = (item.findtext("link") or "").strip()
            pub     = (item.findtext("pubDate") or "").strip()
            combined = (title + " " + desc).lower()
            tags = [kw for kw in NEWS_KEYWORDS if kw in combined]
            mentions = [t for t in _ALL_TICKER_SET if t.lower() in combined.split()]
            items.append({
                "title":           title,
                "summary":         desc[:200],
                "link":            link,
                "published":       pub,
                "source":          source_name,
                "tags":            tags,
                "ticker_mentions": mentions,
            })
    except Exception:
        pass
    return items


@app.get("/intel/news")
def intel_news():
    global _news_cache
    if _news_cache["data"] and (time.time() - _news_cache["ts"]) < 1800:
        return _news_cache["data"]

    all_items = []
    with _TPE(max_workers=3) as ex:
        futures = {ex.submit(_fetch_rss, name, url): name for name, url in NEWS_SOURCES}
        for f in futures:
            all_items.extend(f.result())

    # Sort by pubDate descending (best-effort; keep order if parsing fails)
    def _parse_date(item):
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(item["published"])
        except Exception:
            return datetime.min

    all_items.sort(key=_parse_date, reverse=True)

    result = {"items": all_items[:30], "fetched_at": datetime.utcnow().isoformat()}
    _news_cache["data"] = result
    _news_cache["ts"]   = time.time()
    return result


def _check_statuspage(ticker: str, name: str, url: str) -> dict:
    base = {
        "ticker":              ticker,
        "name":                name,
        "url":                 url,
        "status":              "unknown",
        "indicator":           "none",
        "components_affected": [],
        "checked_at":          datetime.utcnow().isoformat(),
    }
    try:
        if url.endswith(".json"):
            resp = _requests.get(url, timeout=5)
            data = resp.json()
            indicator = data.get("status", {}).get("indicator", "none")
            base["indicator"] = indicator
            base["status"]    = "operational" if indicator == "none" else \
                                "outage"      if indicator in ("major", "critical") else \
                                "degraded"
            affected = [
                c["name"] for c in data.get("components", [])
                if c.get("status", "operational") != "operational"
            ]
            base["components_affected"] = affected
        else:
            # HTTP health check fallback
            resp = _requests.get(url, timeout=5)
            base["indicator"] = "none" if resp.status_code < 400 else "major"
            base["status"]    = "operational" if resp.status_code < 400 else "outage"
    except Exception as e:
        base["status"]    = "unknown"
        base["indicator"] = "unknown"
        base["error"]     = str(e)
    return base


@app.get("/intel/outages")
def intel_outages():
    global _outage_cache
    if _outage_cache["data"] and (time.time() - _outage_cache["ts"]) < 300:
        return _outage_cache["data"]

    results = []
    with _TPE(max_workers=6) as ex:
        futures = {
            ex.submit(_check_statuspage, ticker, name, url): ticker
            for ticker, (name, url) in STATUS_PAGES.items()
        }
        for f in futures:
            results.append(f.result())

    results.sort(key=lambda x: x["ticker"])
    _outage_cache["data"] = results
    _outage_cache["ts"]   = time.time()
    return results


# ── Killer Plays — High-conviction plays from latest scan ──────────────────────

@app.get("/killer-plays")
def get_killer_plays(limit: int = Query(8, ge=1, le=15)):
    """
    Return the highest-conviction plays from the latest scan.
    Criteria: opt_score in top-40% of universe AND lt_score >= 35,
    no active outage/breach. Sorted by combined score (opt*0.6 + lt*0.4).

    Note: thresholds are relative — the top opt_score in the universe typically
    sits between 45-60 depending on market conditions (earnings cycle, IV regime).
    We use the 60th-percentile opt_score as a dynamic floor.
    """
    conn = get_db()

    # Step 1: compute 60th-percentile opt_score from latest scan per ticker
    pct_row = conn.execute("""
        SELECT opt_score FROM (
            SELECT s.opt_score
            FROM scores s
            INNER JOIN (
                SELECT ticker, MAX(scan_id) AS max_scan_id FROM scores GROUP BY ticker
            ) latest ON s.ticker = latest.ticker AND s.scan_id = latest.max_scan_id
            ORDER BY s.opt_score DESC
        )
        LIMIT 1 OFFSET (
            SELECT MAX(1, CAST(COUNT(*)*0.4 AS INTEGER))
            FROM scores s2
            INNER JOIN (
                SELECT ticker, MAX(scan_id) AS max_scan_id FROM scores GROUP BY ticker
            ) latest2 ON s2.ticker = latest2.ticker AND s2.scan_id = latest2.max_scan_id
        )
    """).fetchone()
    # Use dynamic 60th-pct floor, but enforce absolute minimums to avoid noise
    opt_floor = max(40.0, float(pct_row[0]) if pct_row else 40.0)
    lt_floor = 35.0

    rows = conn.execute("""
        SELECT s.ticker, s.price, s.opt_score, s.lt_score, s.rsi, s.days_to_earnings,
               s.threat_score, s.outage_status, s.breach_victim, s.demand_signal,
               s.bb_width, s.vol_ratio, s.sector, s.pct_from_52w_high, s.beta,
               s.iv_30d, s.horizon, s.recommended_expiry, s.iv_rank
        FROM scores s
        INNER JOIN (
            SELECT ticker, MAX(scan_id) AS max_scan_id
            FROM scores GROUP BY ticker
        ) latest ON s.ticker = latest.ticker AND s.scan_id = latest.max_scan_id
        WHERE s.opt_score >= ?
          AND s.lt_score >= ?
          AND (s.threat_score IS NULL OR s.threat_score >= 70)
          AND (s.outage_status IS NULL OR s.outage_status NOT IN ('outage'))
          AND (s.breach_victim IS NULL OR s.breach_victim = 0)
        ORDER BY (s.opt_score * 0.6 + s.lt_score * 0.4) DESC
        LIMIT ?
    """, (opt_floor, lt_floor, limit)).fetchall()
    conn.close()

    results = []
    for r in rows:
        row = dict(r)
        rsi = row.get("rsi") or 50
        dte = row.get("days_to_earnings")
        # Directional signal from RSI
        if rsi > 68:
            row["direction"] = "bearish"
            row["direction_label"] = "📉 Bearish"
        elif rsi < 36:
            row["direction"] = "bullish"
            row["direction_label"] = "📈 Bullish"
        else:
            row["direction"] = "neutral"
            row["direction_label"] = "↔ Neutral"
        # Primary catalyst
        if dte is not None and 5 <= dte <= 30:
            row["catalyst"] = f"⚡ Earnings {dte}d"
        elif row.get("demand_signal"):
            row["catalyst"] = "🌋 Demand Signal"
        elif row.get("bb_width") and row["bb_width"] < 12:
            row["catalyst"] = "⟨⟩ BB Squeeze"
        else:
            row["catalyst"] = "📊 Technical"
        row["combined_score"] = round((row.get("opt_score") or 0) * 0.6 + (row.get("lt_score") or 0) * 0.4, 1)
        results.append(row)

    return {
        "plays": results,
        "total": len(results),
        "timestamp": datetime.now().isoformat(),
    }


# ── Signals Feed — Recent scoring signals for a ticker ────────────────────────

@app.get("/signals/{ticker}/recent")
def get_recent_signals(ticker: str, limit: int = Query(40, ge=5, le=100)):
    """Return recent scoring signals for a ticker from the signals table."""
    t = ticker.upper()
    # Basic ticker validation
    if not t.replace(".", "").isalnum() or len(t) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    conn = get_db()
    rows = conn.execute("""
        SELECT sg.signal_text, sg.impact, sc.timestamp AS scan_ts
        FROM signals sg
        JOIN scans sc ON sg.scan_id = sc.id
        WHERE sg.ticker = ?
        ORDER BY sg.id DESC LIMIT ?
    """, (t, limit)).fetchall()
    conn.close()
    return {"ticker": t, "signals": [dict(r) for r in rows], "total": len(rows)}


# ── Watchlist — Custom ticker tracking ────────────────────────────────────────

class WatchlistAddRequest(BaseModel):
    ticker: str
    notes: Optional[str] = ""
    sector: Optional[str] = "unknown"


@app.get("/watchlist")
def watchlist_list():
    """Return all watchlist items with their latest scan scores."""
    items = get_watchlist()
    if not items:
        return {"items": [], "total": 0}
    conn = get_db()
    for item in items:
        t = item["ticker"]
        score_row = conn.execute("""
            SELECT s.lt_score, s.opt_score, s.price, s.rsi, s.threat_score,
                   s.outage_status, s.sector as scored_sector
            FROM scores s
            INNER JOIN (
                SELECT ticker, MAX(scan_id) AS max_scan_id FROM scores GROUP BY ticker
            ) latest ON s.ticker = latest.ticker AND s.scan_id = latest.max_scan_id
            WHERE s.ticker = ?
        """, (t,)).fetchone()
        if score_row:
            item.update(dict(score_row))
            item["has_scores"] = True
        else:
            item["has_scores"] = False
    conn.close()
    return {"items": items, "total": len(items)}


@app.post("/watchlist")
def watchlist_add(req: WatchlistAddRequest):
    """Add a ticker to the watchlist."""
    ticker = req.ticker.upper().strip()
    # Validate ticker format
    if not ticker or len(ticker) > 10 or not ticker.replace(".", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid ticker format (max 10 chars, alphanumeric)")
    try:
        added = add_to_watchlist(ticker, notes=req.notes or "", sector=req.sector or "unknown")
        return {
            "status": "added" if added else "already_exists",
            "ticker": ticker,
            "message": f"{ticker} {'added to' if added else 'already in'} watchlist",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/watchlist/{ticker}")
def watchlist_remove(ticker: str):
    """Remove a ticker from the watchlist."""
    t = ticker.upper()
    if not t.replace(".", "").isalnum() or len(t) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    remove_from_watchlist(t)
    return {"status": "removed", "ticker": t}


# ── Email Alerts ───────────────────────────────────────────────────────────────

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
ALERT_EMAIL = os.environ.get("ALERT_EMAIL", "")


def _send_email(subject: str, body_html: str) -> bool:
    """Send an HTML email alert. Returns True on success."""
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, ALERT_EMAIL]):
        print("⚠️ Email not configured (set SMTP_HOST, SMTP_USER, SMTP_PASS, ALERT_EMAIL env vars)")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = ALERT_EMAIL
        msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, ALERT_EMAIL, msg.as_string())
        return True
    except Exception as e:
        print(f"⚠️ Email send failed: {e}")
        return False


@app.post("/alerts/send-killer-plays")
def send_killer_plays_alert():
    """Fetch killer plays and send an email alert."""
    if not _check_rate_limit("email_alert", max_calls=3, window_seconds=3600):
        raise HTTPException(status_code=429, detail="Email alert rate limit: max 3/hour")

    # Get top plays
    plays_data = get_killer_plays(limit=8)
    plays = plays_data.get("plays", [])
    if not plays:
        return {"status": "skipped", "message": "No killer plays found meeting criteria"}

    # Build HTML email
    rows_html = ""
    for p in plays:
        rows_html += f"""
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px 12px;font-weight:700;font-family:monospace">{p['ticker']}</td>
          <td style="padding:8px 12px">${p.get('price','—')}</td>
          <td style="padding:8px 12px;color:{'#34c759' if (p.get('opt_score',0))>=65 else '#ff9500'};font-weight:700">{p.get('opt_score','—')}</td>
          <td style="padding:8px 12px;color:#007aff;font-weight:700">{p.get('lt_score','—')}</td>
          <td style="padding:8px 12px">{p.get('catalyst','—')}</td>
          <td style="padding:8px 12px">{p.get('direction_label','—')}</td>
          <td style="padding:8px 12px;font-weight:700">{p.get('combined_score','—')}</td>
        </tr>"""

    body_html = f"""
    <html><body style="font-family:-apple-system,sans-serif;color:#1d1d1f;background:#f5f5f7;padding:0;margin:0">
    <div style="max-width:700px;margin:32px auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">
      <div style="padding:24px 28px;background:linear-gradient(135deg,#007aff,#5856d6)">
        <h1 style="margin:0;color:#fff;font-size:22px">⚡ Augur Killer Plays Alert</h1>
        <p style="margin:6px 0 0;color:rgba(255,255,255,.8);font-size:13px">{datetime.now().strftime('%B %d, %Y at %H:%M UTC')} · {len(plays)} high-conviction opportunities</p>
      </div>
      <div style="padding:24px 28px">
        <p style="font-size:13px;color:#86868b;margin-bottom:16px">These tickers scored ≥55 opt + ≥40 LT with no active threat signals. Review on Augur before acting.</p>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr style="background:#f5f5f7;border-bottom:2px solid #e5e5ea">
            <th style="padding:8px 12px;text-align:left">Ticker</th>
            <th style="padding:8px 12px;text-align:left">Price</th>
            <th style="padding:8px 12px;text-align:left">Opt</th>
            <th style="padding:8px 12px;text-align:left">LT</th>
            <th style="padding:8px 12px;text-align:left">Catalyst</th>
            <th style="padding:8px 12px;text-align:left">Direction</th>
            <th style="padding:8px 12px;text-align:left">Score</th>
          </tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
        <p style="margin-top:20px;font-size:11px;color:#aeaeb2">⚠️ For research only. Not financial advice. Past signals do not guarantee future results.</p>
      </div>
    </div></body></html>"""

    sent = _send_email(f"⚡ Augur: {len(plays)} Killer Plays Found", body_html)
    return {
        "status": "sent" if sent else "email_not_configured",
        "plays_count": len(plays),
        "plays": [p["ticker"] for p in plays],
    }


@app.get("/alerts/config")
def get_alert_config():
    """Check email alert configuration status."""
    return {
        "configured": bool(SMTP_HOST and SMTP_USER and SMTP_PASS and ALERT_EMAIL),
        "smtp_host": SMTP_HOST or "(not set)",
        "alert_email": ALERT_EMAIL or "(not set)",
        "required_env_vars": ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "ALERT_EMAIL"],
    }

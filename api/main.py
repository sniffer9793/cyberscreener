"""
CyberScreener API — FastAPI backend with auth.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, BackgroundTasks, Query, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import time
import hashlib

from core.scanner import run_scan, ALL_TICKERS, CYBER_UNIVERSE
from db.models import (
    init_db, save_scan, get_score_history,
    get_all_scores_for_backtest, get_scan_count, get_db,
)
from backtest.engine import (
    run_full_backtest,
    backtest_score_vs_returns,
    backtest_layer_attribution,
    backtest_earnings_timing,
)

# Config — set CYBERSCREENER_PASSWORD env var in Railway
API_PASSWORD = os.environ.get("CYBERSCREENER_PASSWORD", "cybershield2026")

app = FastAPI(title="CyberScreener API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# Serve dashboard HTML from the API itself
from fastapi.responses import HTMLResponse

def _find_dashboard():
    """Search multiple possible locations for the dashboard file."""
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
    searched = [str(Path(__file__).parent), str(Path(__file__).parent.parent), "/app", "/app/api"]
    return f"<h1>Dashboard not found. Searched: {searched}. __file__={__file__}</h1>"

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
    return {"status": "ok", "scans": get_scan_count()}


# ─── Backfill ───
_backfill_status = {"running": False, "message": "idle"}

@app.post("/backfill")
def trigger_backfill(background_tasks: BackgroundTasks, months: int = Query(6, ge=1, le=12)):
    """Trigger historical backfill. Runs in background."""
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
        from core.scanner import ALL_TICKERS, score_long_term, score_options

        # Step 1: Download all history
        _backfill_status["message"] = f"Downloading price history for {len(ALL_TICKERS)} tickers..."
        data = yf.download(ALL_TICKERS, period="1y", group_by="ticker", progress=False, threads=True)
        if data is None or data.empty:
            _backfill_status["message"] = "Error: Failed to download data"
            _backfill_status["running"] = False
            return

        # Step 2: Download fundamentals
        _backfill_status["message"] = "Fetching fundamentals..."
        fundamentals = {}
        for ticker in ALL_TICKERS:
            try:
                t = yf.Ticker(ticker)
                info = t.info
                fundamentals[ticker] = {
                    "market_cap": info.get("marketCap", 0),
                    "revenue_growth": info.get("revenueGrowth", 0),
                    "gross_margins": info.get("grossMargins", 0),
                    "fcf": info.get("freeCashflow", 0),
                    "ps_ratio": info.get("priceToSalesTrailing12Months"),
                    "pe_ratio": info.get("trailingPE"),
                    "beta": info.get("beta", 1.0),
                    "short_pct": info.get("shortPercentOfFloat", 0) or 0,
                }
                time.sleep(0.2)
            except Exception:
                fundamentals[ticker] = {}

        # Step 3: Simulate weekly scans
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
                (sim_date.strftime("%Y-%m-%d %H:%M:%S"), 0, '{"mode":"backfill"}', "base")
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
                    sma_50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else price
                    sma_200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

                    delta = close.diff()
                    gain = delta.where(delta > 0, 0).rolling(14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                    rs = gain / loss
                    rsi = float((100 - (100 / (1 + rs))).iloc[-1])
                    if np.isnan(rsi): rsi = 50.0

                    rolling_std = float(close.rolling(20).std().iloc[-1])
                    bb_width = (rolling_std * 4) / sma_20 * 100 if sma_20 > 0 else 0

                    vol_ratio = 1.0
                    if "Volume" in td.columns and len(td) >= 20:
                        v20 = td["Volume"].tail(20).mean()
                        v5 = td["Volume"].tail(5).mean()
                        vol_ratio = float(v5 / v20) if v20 > 0 else 1.0

                    p63 = float(close.iloc[-63]) if len(close) >= 63 else price
                    p0 = float(close.iloc[0])
                    hi = float(td["High"].max()) if "High" in td.columns else price
                    lo = float(td["Low"].min()) if "Low" in td.columns else price

                    fund = fundamentals.get(ticker, {})
                    mc = fund.get("market_cap", 0)

                    row = {
                        "ticker": ticker, "price": round(price, 2),
                        "market_cap_b": round(mc / 1e9, 1) if mc else None,
                        "revenue_growth_pct": round(fund.get("revenue_growth", 0) * 100, 1) if fund.get("revenue_growth") else None,
                        "gross_margin_pct": round(fund.get("gross_margins", 0) * 100, 1) if fund.get("gross_margins") else None,
                        "fcf_m": round(fund.get("fcf", 0) / 1e6, 0) if fund.get("fcf") else None,
                        "ps_ratio": round(fund.get("ps_ratio"), 1) if fund.get("ps_ratio") else None,
                        "pe_ratio": round(fund.get("pe_ratio"), 1) if fund.get("pe_ratio") else None,
                        "beta": round(fund.get("beta", 1.0), 2) if fund.get("beta") else None,
                        "short_pct": round(fund.get("short_pct", 0) * 100, 1),
                        "rsi": round(rsi, 1), "sma_20": round(sma_20, 2), "sma_50": round(sma_50, 2),
                        "sma_200": round(sma_200, 2) if sma_200 else None,
                        "bb_width": round(bb_width, 1), "vol_ratio": round(vol_ratio, 2),
                        "perf_3m": round(((price / p63) - 1) * 100, 1),
                        "perf_1y": round(((price / p0) - 1) * 100, 1),
                        "pct_from_52w_high": round(((price / hi) - 1) * 100, 1),
                        "price_52w_high": round(hi, 2), "price_52w_low": round(lo, 2),
                        "iv_30d": None, "days_to_earnings": None,
                        "price_above_sma20": price > sma_20, "price_above_sma50": price > sma_50,
                        "price_above_sma200": price > sma_200 if sma_200 else None,
                    }

                    lt_score, _ = score_long_term(row)
                    opt_score, _ = score_options(row)

                    conn.execute("""
                        INSERT INTO scores (
                            scan_id, ticker, price, market_cap_b,
                            lt_score, opt_score,
                            revenue_growth_pct, gross_margin_pct, ps_ratio, pe_ratio, fcf_m,
                            rsi, sma_20, sma_50, sma_200, bb_width, vol_ratio, iv_30d, beta, short_pct,
                            perf_1y, perf_3m, pct_from_52w_high, days_to_earnings,
                            sec_score, sentiment_score, sentiment_bull_pct, whale_score, pc_ratio,
                            insider_buys_30d, insider_sells_30d
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        scan_id, ticker, row["price"], row.get("market_cap_b"),
                        lt_score, opt_score,
                        row.get("revenue_growth_pct"), row.get("gross_margin_pct"),
                        row.get("ps_ratio"), row.get("pe_ratio"), row.get("fcf_m"),
                        row["rsi"], row["sma_20"], row["sma_50"], row.get("sma_200"),
                        row["bb_width"], row["vol_ratio"], None, row.get("beta"), row.get("short_pct"),
                        row["perf_1y"], row["perf_3m"], row["pct_from_52w_high"], None,
                        0, 0, None, 0, None, 0, 0,
                    ))

                    # Save price + forward prices
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


# In-memory scan status tracking
_scan_status = {"running": False, "last_scan_id": None, "message": ""}


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/api/info")
def api_info():
    return {
        "service": "CyberScreener API",
        "version": "2.0.0",
        "total_scans": get_scan_count(),
    }


@app.get("/tickers")
def get_tickers():
    """List all tickers organized by subsector."""
    return {
        "universe": CYBER_UNIVERSE,
        "all_tickers": ALL_TICKERS,
        "total": len(ALL_TICKERS),
    }


@app.post("/scan", response_model=ScanStatus)
def trigger_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    """Trigger a full scan. Runs in background and saves to DB."""
    if _scan_status["running"]:
        return ScanStatus(status="busy", message="A scan is already running.")

    background_tasks.add_task(_run_scan_background, req)
    return ScanStatus(status="started", message="Scan started in background. Check /scan/status for progress.")


def _run_scan_background(req: ScanRequest):
    """Background scan task."""
    global _scan_status
    _scan_status["running"] = True
    _scan_status["message"] = "Scanning..."

    start_time = time.time()
    tickers = req.tickers or ALL_TICKERS

    try:
        def progress_callback(ticker, i, total):
            _scan_status["message"] = f"Scanning {ticker} ({i+1}/{total})"

        results = run_scan(tickers=tickers, enable_sec=req.enable_sec, callback=progress_callback)
        duration = time.time() - start_time

        intel_layers = []
        if req.enable_sec:
            intel_layers.append("sec")
        if req.enable_sentiment:
            intel_layers.append("sentiment")
        if req.enable_whale:
            intel_layers.append("whale")

        scan_id = save_scan(results, intel_layers=intel_layers, duration_seconds=duration)

        _scan_status["last_scan_id"] = scan_id
        _scan_status["message"] = f"Complete. {len(results)} tickers scanned in {duration:.1f}s."
    except Exception as e:
        _scan_status["message"] = f"Error: {str(e)}"
    finally:
        _scan_status["running"] = False


@app.get("/scan/status")
def scan_status():
    """Check the status of the current/last scan."""
    return _scan_status


@app.get("/scores/{ticker}")
def get_ticker_scores(ticker: str, days: int = Query(90, ge=7, le=365)):
    """Get historical scores for a specific ticker."""
    history = get_score_history(ticker.upper(), days)
    if not history:
        return {"ticker": ticker.upper(), "history": [], "message": "No data found. Run some scans first."}
    return {
        "ticker": ticker.upper(),
        "history": history,
        "data_points": len(history),
    }


@app.get("/scores/latest")
def get_latest_scores(limit: int = Query(50, ge=1, le=100)):
    """Get the most recent scan results."""
    conn = get_db()
    # Get latest scan
    scan = conn.execute("SELECT id, timestamp FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not scan:
        conn.close()
        return {"message": "No scans found. Run a scan first.", "results": []}

    rows = conn.execute("""
        SELECT * FROM scores WHERE scan_id = ? ORDER BY lt_score DESC LIMIT ?
    """, (scan["id"], limit)).fetchall()
    conn.close()

    return {
        "scan_id": scan["id"],
        "scan_timestamp": scan["timestamp"],
        "results": [dict(r) for r in rows],
    }


@app.get("/backtest")
def run_backtest_all(
    days: int = Query(180, ge=30, le=365),
    forward_period: int = Query(30, ge=7, le=90),
):
    """Run complete backtest — all three analyses."""
    return run_full_backtest(days, forward_period)


@app.get("/backtest/score-vs-returns")
def backtest_scores(
    days: int = Query(180, ge=30, le=365),
    forward_period: int = Query(30, ge=7, le=90),
):
    """Q1: Did scores predict actual returns? Quintile analysis."""
    return backtest_score_vs_returns(days, forward_period)


@app.get("/backtest/layer-attribution")
def backtest_layers(
    days: int = Query(180, ge=30, le=365),
    forward_period: int = Query(30, ge=7, le=90),
):
    """Q2: Which intelligence layers added alpha?"""
    return backtest_layer_attribution(days, forward_period)


@app.get("/backtest/earnings-timing")
def backtest_earnings(days: int = Query(180, ge=30, le=365)):
    """Q3: Optimal entry timing relative to earnings?"""
    return backtest_earnings_timing(days)


@app.get("/stats")
def get_stats():
    """Database statistics."""
    conn = get_db()
    stats = {}

    stats["total_scans"] = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
    stats["total_score_records"] = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
    stats["total_signals"] = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    stats["total_price_snapshots"] = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    stats["unique_tickers_tracked"] = conn.execute("SELECT COUNT(DISTINCT ticker) FROM scores").fetchone()[0]

    first_scan = conn.execute("SELECT MIN(timestamp) FROM scans").fetchone()[0]
    last_scan = conn.execute("SELECT MAX(timestamp) FROM scans").fetchone()[0]
    stats["first_scan"] = first_scan
    stats["last_scan"] = last_scan

    # Top scored tickers (latest scan)
    latest = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if latest:
        top_lt = conn.execute("""
            SELECT ticker, lt_score, opt_score FROM scores
            WHERE scan_id = ? ORDER BY lt_score DESC LIMIT 5
        """, (latest[0],)).fetchall()
        stats["top_lt_scores"] = [{"ticker": r[0], "lt_score": r[1], "opt_score": r[2]} for r in top_lt]

        top_opt = conn.execute("""
            SELECT ticker, opt_score, lt_score FROM scores
            WHERE scan_id = ? ORDER BY opt_score DESC LIMIT 5
        """, (latest[0],)).fetchall()
        stats["top_opt_scores"] = [{"ticker": r[0], "opt_score": r[1], "lt_score": r[2]} for r in top_opt]

    conn.close()
    return stats

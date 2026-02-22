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
    run_scan, ALL_TICKERS, CYBER_UNIVERSE,
    fetch_options_chain, generate_plays, fetch_ticker_data,
    score_long_term, score_options, get_weights, set_weights,
    DEFAULT_LT_WEIGHTS, DEFAULT_OPT_WEIGHTS,
)
from db.models import (
    init_db, save_scan, get_score_history,
    get_all_scores_for_backtest, get_scan_count, get_db,
    save_score_weights, get_latest_weights,
)
from backtest.engine import (
    run_full_backtest,
    backtest_score_vs_returns,
    backtest_layer_attribution,
    backtest_earnings_timing,
    calibrate_weights,
)

API_PASSWORD = os.environ.get("CYBERSCREENER_PASSWORD", "cybershield2026")

app = FastAPI(title="CyberScreener API", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

init_db()

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
        "service": "CyberScreener API",
        "version": "3.0.0",
        "scoring": "v2",
        "total_scans": get_scan_count(),
        "active_weights": get_weights(),
    }

@app.get("/tickers")
def get_tickers():
    return {"universe": CYBER_UNIVERSE, "all_tickers": ALL_TICKERS, "total": len(ALL_TICKERS)}

@app.post("/scan", response_model=ScanStatus)
def trigger_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    if _scan_status["running"]:
        return ScanStatus(status="busy", message="A scan is already running.")
    background_tasks.add_task(_run_scan_background, req)
    return ScanStatus(status="started", message="Scan started. Check /scan/status.")

def _run_scan_background(req: ScanRequest):
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
def get_latest_scores(limit: int = Query(50, ge=1, le=100)):
    conn = get_db()
    scan = conn.execute("SELECT id, timestamp FROM scans WHERE intel_layers != 'base' ORDER BY id DESC LIMIT 1").fetchone()
    if not scan:
        scan = conn.execute("SELECT id, timestamp FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not scan:
        conn.close()
        return {"message": "No scans found.", "results": []}
    rows = conn.execute("SELECT * FROM scores WHERE scan_id = ? ORDER BY lt_score DESC LIMIT ?",
                        (scan["id"], limit)).fetchall()
    conn.close()
    return {"scan_id": scan["id"], "scan_timestamp": scan["timestamp"], "results": [dict(r) for r in rows]}

@app.get("/scores/{ticker}")
def get_ticker_scores(ticker: str, days: int = Query(90, ge=7, le=365)):
    history = get_score_history(ticker.upper(), days)
    if not history:
        return {"ticker": ticker.upper(), "history": [], "message": "No data found."}
    return {"ticker": ticker.upper(), "history": history, "data_points": len(history)}


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

@app.get("/debug/options/{ticker}")
def debug_options(ticker: str):
    """Test endpoint to isolate options chain fetch on Railway."""
    import yfinance as yf
    import time
    result = {"ticker": ticker, "steps": []}
    try:
        t = yf.Ticker(ticker)
        result["steps"].append("ticker_created")
        dates = t.options
        result["steps"].append(f"options_dates={list(dates)[:3] if dates else []}")
        if dates:
            chain = t.option_chain(dates[0])
            result["steps"].append(f"chain_fetched_calls={len(chain.calls)}_puts={len(chain.puts)}")
    except Exception as e:
        result["error"] = str(e)
    return result

@app.get("/debug/chain/{ticker}")
def debug_chain(ticker: str):
    import yfinance as yf
    t = yf.Ticker(ticker)
    try:
        dates = t.options
        if not dates:
            return {"error": "no options dates"}
        chain = t.option_chain(dates[0])
        calls = chain.calls[["strike","volume","openInterest","impliedVolatility","bid","ask"]].dropna()
        # Top 5 by volume
        top = calls.nlargest(5, "volume").to_dict("records")
        total_vol = int(calls["volume"].sum())
        max_vol = int(calls["volume"].max())
        max_oi = int(calls["openInterest"].max())
        return {
            "expiry": dates[0],
            "total_call_volume": total_vol,
            "max_single_strike_volume": max_vol,
            "max_open_interest": max_oi,
            "top_5_by_volume": top
        }
    except Exception as e:
        return {"error": str(e)}

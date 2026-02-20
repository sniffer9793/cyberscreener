"""
CyberScreener API — Production deployment.
Serves both the API and the frontend dashboard.
Password-protected via simple token auth.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, BackgroundTasks, Query, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import hashlib
import time

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

# ─── Config ───
# Set your password via environment variable, or default for dev
AUTH_PASSWORD = os.environ.get("CYBERSCREENER_PASSWORD", "cyber2026")
AUTH_TOKEN = hashlib.sha256(AUTH_PASSWORD.encode()).hexdigest()[:32]

app = FastAPI(title="CyberScreener API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# ─── Auth ───
def verify_auth(request: Request):
    """Check for auth token in cookie or header."""
    token = request.cookies.get("cs_auth") or request.headers.get("X-Auth-Token")
    if token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

class LoginRequest(BaseModel):
    password: str

@app.post("/api/login")
def login(req: LoginRequest):
    if req.password == AUTH_PASSWORD:
        response = JSONResponse({"status": "ok", "token": AUTH_TOKEN})
        response.set_cookie("cs_auth", AUTH_TOKEN, httponly=True, samesite="lax", max_age=86400 * 30)
        return response
    raise HTTPException(status_code=401, detail="Wrong password")

@app.get("/api/check-auth")
def check_auth(request: Request):
    token = request.cookies.get("cs_auth") or request.headers.get("X-Auth-Token")
    if token == AUTH_TOKEN:
        return {"authenticated": True}
    return {"authenticated": False}

# ─── Models ───
class ScanRequest(BaseModel):
    tickers: Optional[list[str]] = None
    enable_sec: bool = True
    enable_sentiment: bool = False
    enable_whale: bool = False

_scan_status = {"running": False, "last_scan_id": None, "message": ""}

# ─── Protected API Endpoints ───
@app.get("/api/tickers")
def get_tickers(_=Depends(verify_auth)):
    return {"universe": CYBER_UNIVERSE, "all_tickers": ALL_TICKERS, "total": len(ALL_TICKERS)}

@app.post("/api/scan")
def trigger_scan(req: ScanRequest, background_tasks: BackgroundTasks, _=Depends(verify_auth)):
    if _scan_status["running"]:
        return {"status": "busy", "message": "Scan already running."}
    background_tasks.add_task(_run_scan_background, req)
    return {"status": "started", "message": "Scan started."}

def _run_scan_background(req: ScanRequest):
    global _scan_status
    _scan_status["running"] = True
    _scan_status["message"] = "Scanning..."
    start_time = time.time()
    tickers = req.tickers or ALL_TICKERS
    try:
        def cb(ticker, i, total):
            _scan_status["message"] = f"Scanning {ticker} ({i+1}/{total})"
        results = run_scan(tickers=tickers, enable_sec=req.enable_sec, callback=cb)
        duration = time.time() - start_time
        intel_layers = []
        if req.enable_sec: intel_layers.append("sec")
        scan_id = save_scan(results, intel_layers=intel_layers, duration_seconds=duration)
        _scan_status["last_scan_id"] = scan_id
        _scan_status["message"] = f"Complete. {len(results)} tickers in {duration:.1f}s."
    except Exception as e:
        _scan_status["message"] = f"Error: {str(e)}"
    finally:
        _scan_status["running"] = False

@app.get("/api/scan/status")
def scan_status(_=Depends(verify_auth)):
    return _scan_status

@app.get("/api/scores/{ticker}")
def get_ticker_scores(ticker: str, days: int = Query(90, ge=7, le=365), _=Depends(verify_auth)):
    history = get_score_history(ticker.upper(), days)
    return {"ticker": ticker.upper(), "history": history, "data_points": len(history)}

@app.get("/api/scores/latest")
def get_latest_scores(limit: int = Query(50, ge=1, le=100), _=Depends(verify_auth)):
    conn = get_db()
    scan = conn.execute("SELECT id, timestamp FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not scan:
        conn.close()
        return {"message": "No scans found.", "results": []}
    rows = conn.execute("SELECT * FROM scores WHERE scan_id = ? ORDER BY lt_score DESC LIMIT ?", (scan["id"], limit)).fetchall()
    conn.close()
    return {"scan_id": scan["id"], "scan_timestamp": scan["timestamp"], "results": [dict(r) for r in rows]}

@app.get("/api/backtest")
def run_backtest_all(days: int = Query(180, ge=30, le=365), forward_period: int = Query(30, ge=7, le=90), _=Depends(verify_auth)):
    return run_full_backtest(days, forward_period)

@app.get("/api/backtest/score-vs-returns")
def backtest_scores(days: int = Query(180, ge=30, le=365), forward_period: int = Query(30, ge=7, le=90), _=Depends(verify_auth)):
    return backtest_score_vs_returns(days, forward_period)

@app.get("/api/backtest/layer-attribution")
def backtest_layers(days: int = Query(180, ge=30, le=365), forward_period: int = Query(30, ge=7, le=90), _=Depends(verify_auth)):
    return backtest_layer_attribution(days, forward_period)

@app.get("/api/backtest/earnings-timing")
def backtest_earnings(days: int = Query(180, ge=30, le=365), _=Depends(verify_auth)):
    return backtest_earnings_timing(days)

@app.get("/api/stats")
def get_stats(_=Depends(verify_auth)):
    conn = get_db()
    stats = {}
    stats["total_scans"] = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
    stats["total_score_records"] = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
    stats["total_signals"] = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    stats["total_price_snapshots"] = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    stats["unique_tickers_tracked"] = conn.execute("SELECT COUNT(DISTINCT ticker) FROM scores").fetchone()[0]
    stats["first_scan"] = conn.execute("SELECT MIN(timestamp) FROM scans").fetchone()[0]
    stats["last_scan"] = conn.execute("SELECT MAX(timestamp) FROM scans").fetchone()[0]
    latest = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if latest:
        top_lt = conn.execute("SELECT ticker, lt_score, opt_score FROM scores WHERE scan_id = ? ORDER BY lt_score DESC LIMIT 5", (latest[0],)).fetchall()
        stats["top_lt_scores"] = [{"ticker": r[0], "lt_score": r[1], "opt_score": r[2]} for r in top_lt]
        top_opt = conn.execute("SELECT ticker, opt_score, lt_score FROM scores WHERE scan_id = ? ORDER BY opt_score DESC LIMIT 5", (latest[0],)).fetchall()
        stats["top_opt_scores"] = [{"ticker": r[0], "opt_score": r[1], "lt_score": r[2]} for r in top_opt]
    conn.close()
    return stats

# ─── Serve Frontend ───
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CyberScreener</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700;800&family=DM+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0e17;color:#e2e8f0;font-family:'DM Sans',-apple-system,sans-serif}
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-track{background:#0f1520}::-webkit-scrollbar-thumb{background:#243049;border-radius:3px}
code{font-family:'JetBrains Mono',monospace;background:#141c2b;padding:2px 6px;border-radius:4px;font-size:12px}
.mono{font-family:'JetBrains Mono',monospace}
.login-wrap{display:flex;align-items:center;justify-content:center;min-height:100vh}
.login-box{background:#0f1520;border:1px solid #1a2235;border-radius:12px;padding:40px;width:360px;text-align:center}
.login-box h1{font-size:20px;font-weight:800;color:#00e5a0;margin-bottom:4px}
.login-box p{font-size:12px;color:#64748b;margin-bottom:24px}
.login-box input{width:100%;padding:12px 16px;background:#0a0e17;border:1px solid #243049;border-radius:8px;color:#e2e8f0;font-size:14px;outline:none;margin-bottom:12px;font-family:'JetBrains Mono',monospace}
.login-box input:focus{border-color:#00e5a040}
.login-box button{width:100%;padding:12px;background:#00e5a015;border:1px solid #00e5a040;border-radius:8px;color:#00e5a0;font-size:13px;font-weight:700;cursor:pointer;font-family:'JetBrains Mono',monospace}
.login-box button:hover{background:#00e5a025}
.login-err{color:#ff3b5c;font-size:12px;margin-top:8px}
.hdr{padding:16px 28px;border-bottom:1px solid #1a2235;display:flex;align-items:center;justify-content:space-between;background:linear-gradient(180deg,#0f1520,#0a0e17)}
.tabs{padding:12px 28px;display:flex;gap:8px;border-bottom:1px solid #1a2235}
.tab{padding:10px 20px;background:transparent;border:1px solid #1a2235;border-radius:8px;color:#64748b;font-size:13px;font-weight:500;cursor:pointer;font-family:'JetBrains Mono',monospace;display:flex;align-items:center;gap:6px}
.tab.on{background:#00e5a012;border-color:#00e5a040;color:#00e5a0;font-weight:700}
.main{padding:24px 28px;max-width:1280px;margin:0 auto}
.card{background:#0f1520;border:1px solid #1a2235;border-radius:10px;padding:20px}
.grid{display:grid;gap:12px}
.g5{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.g2{grid-template-columns:1fr 1fr}
.metric{padding:14px 16px;background:#0f1520;border-radius:8px;border:1px solid #1a2235}
.metric-label{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.metric-val{font-size:26px;font-weight:800;font-family:'JetBrains Mono',monospace;line-height:1}
.metric-sub{font-size:11px;color:#64748b;margin-top:4px}
.sbar{display:flex;align-items:center;gap:8px}
.sbar-track{flex:1;height:6px;background:#1a2235;border-radius:3px;overflow:hidden}
.sbar-fill{height:100%;border-radius:3px;transition:width 0.6s ease}
.sbar-num{font-size:13px;font-weight:700;font-family:'JetBrains Mono',monospace;min-width:28px}
.row{display:grid;grid-template-columns:20px 60px 1fr 70px;align-items:center;gap:8px;padding:4px 0}
.row-tk{font-size:13px;font-weight:700;color:#e2e8f0;font-family:'JetBrains Mono',monospace}
.dim{color:#64748b}.mid{color:#94a3b8}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;letter-spacing:0.5px}
.sec-title{font-size:18px;font-weight:800;letter-spacing:-0.3px;margin-bottom:2px}
.sec-sub{font-size:12px;color:#64748b}
.btn-scan{padding:8px 18px;border-radius:6px;border:1px solid #00e5a040;background:#00e5a015;color:#00e5a0;font-size:12px;font-weight:700;cursor:pointer;font-family:'JetBrains Mono',monospace}
.btn-period{padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;font-family:'JetBrains Mono',monospace;border:1px solid #1a2235;background:#0f1520;color:#64748b}
.btn-period.on{background:#00e5a015;border-color:#00e5a040;color:#00e5a0}
.ticker-list{width:320px;flex-shrink:0;max-height:70vh;overflow-y:auto}
.ticker-row{display:grid;grid-template-columns:54px 1fr 44px 44px;align-items:center;gap:6px;padding:8px 10px;border-radius:6px;cursor:pointer;border-left:3px solid transparent}
.ticker-row:hover{background:#141c2b}
.ticker-row.sel{background:#00e5a010;border-left-color:#00e5a0}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.dot-on{background:#00e5a0;box-shadow:0 0 8px #00e5a060}.dot-off{background:#ff3b5c}
.offline-bar{padding:12px 28px;background:#ff3b5c30;border-bottom:1px solid #ff3b5c30;font-size:12px;color:#ff3b5c}
.chart-placeholder{height:250px;display:flex;align-items:center;justify-content:center;color:#64748b;font-size:13px;border:1px dashed #243049;border-radius:8px;margin-top:8px}
</style>
</head>
<body>
<div id="app"></div>
<script>
// ─── Globals ───
let authToken = null;
let currentTab = 'overview';
let appData = { stats: null, latest: null, backtest: null, scanStatus: null, online: null };

const $ = sel => document.querySelector(sel);

async function apiCall(path) {
  try {
    const opts = { headers: {} };
    if (authToken) opts.headers['X-Auth-Token'] = authToken;
    const r = await fetch(path, opts);
    if (r.status === 401) { showLogin(); return null; }
    if (!r.ok) return null;
    return await r.json();
  } catch(e) { return null; }
}

async function apiPost(path, body) {
  try {
    const r = await fetch(path, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Auth-Token': authToken || '' },
      body: JSON.stringify(body),
    });
    if (r.status === 401) { showLogin(); return null; }
    return await r.json();
  } catch(e) { return null; }
}

// ─── Auth ───
function showLogin(err) {
  $('#app').innerHTML = `
    <div class="login-wrap">
      <div class="login-box">
        <div style="font-size:32px;margin-bottom:12px">🛡️</div>
        <h1>CyberScreener</h1>
        <p>Investment Intelligence Dashboard</p>
        <input type="password" id="pw" placeholder="Enter password" onkeydown="if(event.key==='Enter')doLogin()">
        <button onclick="doLogin()">▶ Access Dashboard</button>
        ${err ? '<div class="login-err">' + err + '</div>' : ''}
      </div>
    </div>`;
  setTimeout(() => { const el = $('#pw'); if(el) el.focus(); }, 100);
}

async function doLogin() {
  const pw = $('#pw')?.value;
  if (!pw) return;
  const r = await apiPost('/api/login', { password: pw });
  if (r && r.token) {
    authToken = r.token;
    await loadDashboard();
  } else {
    showLogin('Wrong password');
  }
}

// ─── Data Loading ───
async function loadDashboard() {
  $('#app').innerHTML = '<div style="padding:60px;text-align:center;color:#64748b">Loading dashboard...</div>';
  
  const [stats, latest, bt, auth] = await Promise.all([
    apiCall('/api/stats'),
    apiCall('/api/scores/latest?limit=50'),
    apiCall('/api/backtest?days=180&forward_period=30'),
    apiCall('/api/check-auth'),
  ]);

  if (!auth || !auth.authenticated) { showLogin(); return; }
  
  appData.stats = stats;
  appData.latest = latest;
  appData.backtest = bt;
  appData.online = !!stats;
  
  renderApp();
}

// ─── Rendering ───
function scoreColor(s, hi=60, mid=35) { return s >= hi ? '#00e5a0' : s >= mid ? '#ffb020' : '#ff3b5c'; }
function scoreBar(score, max=100) {
  const pct = Math.max(0, Math.min(100, (score/max)*100));
  const c = scoreColor(score);
  return `<div class="sbar"><div class="sbar-track"><div class="sbar-fill" style="width:${pct}%;background:${c}"></div></div><span class="sbar-num" style="color:${c}">${score}</span></div>`;
}
function metric(label, value, color, sub) {
  return `<div class="metric"><div class="metric-label">${label}</div><div class="metric-val" style="color:${color||'#e2e8f0'}">${value}</div>${sub?'<div class="metric-sub">'+sub+'</div>':''}</div>`;
}

function renderApp() {
  const s = appData.stats || {};
  $('#app').innerHTML = `
    <div class="hdr">
      <div style="display:flex;align-items:center;gap:12px">
        <span style="font-size:22px">🛡️</span>
        <div>
          <div style="font-size:18px;font-weight:800;color:#00e5a0;letter-spacing:-0.5px">CyberScreener</div>
          <div style="font-size:10px;color:#64748b;letter-spacing:2px;text-transform:uppercase">Investment Intelligence</div>
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:12px">
        <span class="dot ${appData.online ? 'dot-on' : 'dot-off'}"></span>
        <span class="dim" style="font-size:11px">${appData.online ? 'Online' : 'Offline'}</span>
        <button class="btn-scan" id="scanBtn" onclick="triggerScan()">▶ Run Scan</button>
      </div>
    </div>
    <nav class="tabs">
      <button class="tab ${currentTab==='overview'?'on':''}" onclick="switchTab('overview')">◉ Overview</button>
      <button class="tab ${currentTab==='scores'?'on':''}" onclick="switchTab('scores')">◆ Score Explorer</button>
      <button class="tab ${currentTab==='backtest'?'on':''}" onclick="switchTab('backtest')">◈ Backtest</button>
    </nav>
    <div class="main" id="content"></div>
    <footer style="padding:16px 28px;border-top:1px solid #1a2235;text-align:center">
      <span style="font-size:10px;color:#64748b">CyberScreener v2.0 — Not financial advice.</span>
    </footer>`;
  
  renderTab();
}

function switchTab(t) { currentTab = t; renderApp(); }

function renderTab() {
  if (currentTab === 'overview') renderOverview();
  else if (currentTab === 'scores') renderScores();
  else if (currentTab === 'backtest') renderBacktest();
}

// ─── Overview ───
function renderOverview() {
  const s = appData.stats || {};
  const results = appData.latest?.results || [];
  const topLT = results.slice(0, 10);
  const topOpt = [...results].sort((a,b) => b.opt_score - a.opt_score).slice(0, 10);
  const rsiSorted = [...results].sort((a,b) => a.rsi - b.rsi);

  let html = `<div class="grid g5">
    ${metric('Total Scans', s.total_scans || 0)}
    ${metric('Tickers', s.unique_tickers_tracked || 0)}
    ${metric('Score Records', (s.total_score_records||0).toLocaleString())}
    ${metric('Price Snapshots', (s.total_price_snapshots||0).toLocaleString())}
    ${metric('Last Scan', s.last_scan ? new Date(s.last_scan).toLocaleDateString() : '—')}
  </div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card">
      <div class="sec-title">📈 Long-Term Scores</div>
      <div class="sec-sub" style="margin-bottom:12px">Latest scan rankings</div>
      ${topLT.map((r,i) => `<div class="row">
        <span class="dim" style="font-size:11px">${i+1}</span>
        <span class="row-tk">${r.ticker}</span>
        ${scoreBar(r.lt_score)}
        <span class="dim" style="font-size:12px;text-align:right">$${r.price}</span>
      </div>`).join('')}
    </div>
    <div class="card">
      <div class="sec-title">⚡ Options Scores</div>
      <div class="sec-sub" style="margin-bottom:12px">Latest scan rankings</div>
      ${topOpt.map((r,i) => `<div class="row">
        <span class="dim" style="font-size:11px">${i+1}</span>
        <span class="row-tk">${r.ticker}</span>
        ${scoreBar(r.opt_score)}
        <span class="dim" style="font-size:12px;text-align:right">RSI ${r.rsi||'—'}</span>
      </div>`).join('')}
    </div>
  </div>`;

  // RSI heatmap (CSS bars, no charting lib needed)
  if (rsiSorted.length > 0) {
    html += `<div class="card" style="margin-top:16px">
      <div class="sec-title">RSI Heatmap</div>
      <div class="sec-sub" style="margin-bottom:12px">Sector technicals overview</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">
        ${rsiSorted.map(r => {
          const c = r.rsi < 30 ? '#00e5a0' : r.rsi > 70 ? '#ff3b5c' : '#ffb020';
          return `<div style="text-align:center;width:${Math.max(100/rsiSorted.length*3, 28)}px" title="${r.ticker}: RSI ${r.rsi}">
            <div style="height:${Math.max(r.rsi * 1.5, 8)}px;background:${c};opacity:0.7;border-radius:3px 3px 0 0;margin:0 2px;min-height:4px"></div>
            <div style="font-size:8px;color:#64748b;margin-top:2px;transform:rotate(-45deg);white-space:nowrap" class="mono">${r.ticker}</div>
          </div>`;
        }).join('')}
      </div>
    </div>`;
  }

  $('#content').innerHTML = html;
}

// ─── Score Explorer ───
let selectedTicker = null;
let tickerHistory = null;

function renderScores() {
  const results = appData.latest?.results || [];

  let detail = '<div class="card" style="padding:40px;text-align:center"><div class="dim">← Select a ticker to view history</div></div>';
  
  if (selectedTicker && tickerHistory?.history?.length) {
    const h = tickerHistory.history;
    const latest = h[h.length - 1];
    const first = h[0];
    const ltChange = latest.lt_score - first.lt_score;
    const priceChange = latest.price && first.price ? ((latest.price / first.price - 1) * 100).toFixed(1) : null;
    
    detail = `<div class="card">
      <div class="sec-title">${selectedTicker} — Score History</div>
      <div class="sec-sub">${tickerHistory.data_points} data points</div>
      <div class="grid g2" style="margin-top:16px">
        ${metric('Current LT Score', latest.lt_score, scoreColor(latest.lt_score))}
        ${metric('Current Opt Score', latest.opt_score, scoreColor(latest.opt_score, 40, 25))}
        ${metric('LT Score Change', (ltChange >= 0 ? '+' : '') + ltChange, ltChange >= 0 ? '#00e5a0' : '#ff3b5c', 'Over tracking period')}
        ${metric('Price', '$' + latest.price, '#e2e8f0', priceChange ? priceChange + '% over period' : '')}
      </div>
      <div style="margin-top:20px">
        <div style="font-size:13px;font-weight:700;margin-bottom:8px">Score Trend</div>
        ${h.map((p, i) => {
          const date = new Date(p.timestamp).toLocaleDateString('en-US', {month:'short',day:'numeric'});
          const ltW = Math.max(0, Math.min(100, p.lt_score));
          const optW = Math.max(0, Math.min(100, p.opt_score));
          return i % Math.max(1, Math.floor(h.length / 20)) === 0 ? `<div style="display:grid;grid-template-columns:60px 1fr 1fr 40px 40px;align-items:center;gap:6px;padding:2px 0">
            <span class="dim" style="font-size:10px">${date}</span>
            <div style="height:4px;background:#1a2235;border-radius:2px;overflow:hidden"><div style="width:${ltW}%;height:100%;background:#00e5a0;border-radius:2px"></div></div>
            <div style="height:4px;background:#1a2235;border-radius:2px;overflow:hidden"><div style="width:${optW}%;height:100%;background:#3b82f6;border-radius:2px"></div></div>
            <span class="mono" style="font-size:10px;color:#00e5a0">${p.lt_score}</span>
            <span class="mono" style="font-size:10px;color:#3b82f6">${p.opt_score}</span>
          </div>` : '';
        }).join('')}
        <div style="display:flex;gap:16px;margin-top:8px">
          <span style="font-size:10px;color:#00e5a0">■ LT Score</span>
          <span style="font-size:10px;color:#3b82f6">■ Opt Score</span>
        </div>
      </div>
    </div>`;
  } else if (selectedTicker) {
    detail = '<div class="card" style="padding:40px;text-align:center"><div class="dim">Loading...</div></div>';
  }

  $('#content').innerHTML = `<div style="display:flex;gap:16px;min-height:60vh">
    <div class="card ticker-list" style="padding:12px">
      <div class="dim" style="font-size:11px;text-transform:uppercase;letter-spacing:1px;padding:4px 8px;margin-bottom:8px">${results.length} tickers</div>
      ${results.map(r => `<div class="ticker-row ${selectedTicker===r.ticker?'sel':''}" onclick="selectTicker('${r.ticker}')">
        <span class="row-tk">${r.ticker}</span>
        <span class="dim" style="font-size:11px">$${r.price}</span>
        <span class="badge" style="background:${scoreColor(r.lt_score)}18;color:${scoreColor(r.lt_score)};border:1px solid ${scoreColor(r.lt_score)}30">${r.lt_score}</span>
        <span class="badge" style="background:${scoreColor(r.opt_score,40,25)}18;color:${scoreColor(r.opt_score,40,25)};border:1px solid ${scoreColor(r.opt_score,40,25)}30">${r.opt_score}</span>
      </div>`).join('')}
    </div>
    <div style="flex:1">${detail}</div>
  </div>`;
}

async function selectTicker(t) {
  selectedTicker = t;
  tickerHistory = null;
  renderScores();
  const d = await apiCall(`/api/scores/${t}?days=180`);
  if (d) { tickerHistory = d; renderScores(); }
}

// ─── Backtest ───
let btPeriod = 30;

function renderBacktest() {
  const d = appData.backtest;
  if (!d) {
    $('#content').innerHTML = '<div class="card" style="padding:40px;text-align:center"><div style="font-size:36px;margin-bottom:12px">📊</div><div style="font-size:14px;font-weight:600">No backtest data yet</div><div class="dim" style="margin-top:6px">Run the backfill script first.</div></div>';
    return;
  }

  const sd = d.score_vs_returns || {};
  const ld = d.layer_attribution || {};
  const ed = d.earnings_timing || {};

  let html = `<div style="display:flex;gap:8px;align-items:center;margin-bottom:20px">
    <span class="dim" style="font-size:12px">Forward period:</span>
    ${[14,30,60].map(p => `<button class="btn-period ${btPeriod===p?'on':''}" onclick="changePeriod(${p})">${p}d</button>`).join('')}
    <span class="dim" style="font-size:11px;margin-left:auto">${sd.total_observations||0} observations</span>
  </div>`;

  // Correlations
  if (sd.lt_correlation != null) {
    const ltC = sd.lt_correlation;
    const optC = sd.opt_correlation;
    html += `<div class="grid g2">
      ${metric('LT Score ↔ Return', ltC?.toFixed(3)||'—', ltC > 0.1 ? '#00e5a0' : ltC < -0.05 ? '#ff3b5c' : '#ffb020', ltC > 0.15 ? 'Strong signal ✓' : ltC > 0.05 ? 'Weak signal' : 'No signal yet')}
      ${metric('Opt Score ↔ Return', optC?.toFixed(3)||'—', optC > 0.1 ? '#00e5a0' : optC < -0.05 ? '#ff3b5c' : '#ffb020')}
    </div>`;
  }

  // Quintile analysis
  const ltQ = sd['Long-Term Score'];
  if (ltQ && !ltQ.error) {
    html += `<div class="card" style="margin-top:16px">
      <div class="sec-title">Score Quintile → Avg Return</div>
      <div class="sec-sub">Does scoring predict ${btPeriod}-day returns?</div>
      <div style="display:flex;gap:8px;align-items:flex-end;margin-top:16px;height:200px;padding-bottom:30px">
        ${Object.entries(ltQ).map(([label, s]) => {
          const maxR = Math.max(...Object.values(ltQ).map(v => Math.abs(v.avg_return || 0)), 1);
          const h = Math.abs(s.avg_return || 0) / maxR * 150;
          const c = (s.avg_return || 0) >= 0 ? '#00e5a0' : '#ff3b5c';
          const isNeg = (s.avg_return || 0) < 0;
          return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:4px">
            <span class="mono" style="font-size:11px;color:${c};font-weight:700">${(s.avg_return||0) > 0 ? '+' : ''}${(s.avg_return||0).toFixed(1)}%</span>
            <div style="width:80%;height:${Math.max(h,4)}px;background:${c};opacity:0.75;border-radius:4px 4px ${isNeg?'4px 4px':'0 0'}"></div>
            <span class="dim" style="font-size:9px;text-align:center">${label}</span>
            <span class="dim" style="font-size:8px">n=${s.count} | ${(s.win_rate||0).toFixed(0)}%w</span>
          </div>`;
        }).join('')}
      </div>
    </div>`;
  }

  // Layer attribution
  const layers = [['sec_filings','SEC Filings'],['insider_buying','Insider Buying'],['sentiment','Sentiment'],['whale_flow','Whale Flow']];
  const layerData = layers.filter(([k]) => ld[k]?.alpha != null).map(([k,l]) => ({name:l, alpha:ld[k].alpha}));
  
  if (layerData.length > 0) {
    const maxA = Math.max(...layerData.map(d => Math.abs(d.alpha)), 1);
    html += `<div class="card" style="margin-top:16px">
      <div class="sec-title">Intelligence Layer Alpha</div>
      <div class="sec-sub">Return difference: bullish vs bearish/absent</div>
      <div style="margin-top:16px">
        ${layerData.map(d => {
          const c = d.alpha >= 0 ? '#00e5a0' : '#ff3b5c';
          const w = Math.abs(d.alpha) / maxA * 60;
          return `<div style="display:grid;grid-template-columns:120px 1fr 60px;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid #1a2235">
            <span class="mid" style="font-size:12px">${d.name}</span>
            <div style="height:20px;display:flex;align-items:center;justify-content:${d.alpha>=0?'flex-start':'flex-end'}">
              <div style="width:${Math.max(w,4)}%;height:12px;background:${c};opacity:0.75;border-radius:4px"></div>
            </div>
            <span class="mono" style="font-size:12px;color:${c};font-weight:700;text-align:right">${d.alpha > 0 ? '+' : ''}${d.alpha.toFixed(1)}%</span>
          </div>`;
        }).join('')}
      </div>
    </div>`;
  }

  // Earnings timing
  if (ed.timing_buckets) {
    const buckets = Object.entries(ed.timing_buckets).filter(([,s]) => s.count > 0);
    if (buckets.length > 0) {
      html += `<div class="card" style="margin-top:16px">
        <div class="sec-title">Earnings Entry Timing</div>
        <div class="sec-sub">Best entry: ${ed.best_entry_window || '—'}</div>
        <div style="display:grid;grid-template-columns:repeat(${buckets.length}, 1fr);gap:12px;margin-top:16px">
          ${buckets.map(([label, s]) => `<div style="text-align:center">
            <div class="dim" style="font-size:11px;margin-bottom:8px">${label}</div>
            <div class="mono" style="font-size:18px;font-weight:800;color:${(s.avg_return_14d||0)>=0?'#3b82f6':'#ff3b5c'}">${s.avg_return_14d!=null?((s.avg_return_14d>=0?'+':'')+s.avg_return_14d.toFixed(1)+'%'):'—'}</div>
            <div class="dim" style="font-size:10px">14d return</div>
            <div class="mono" style="font-size:14px;color:${(s.avg_return_30d||0)>=0?'#a855f7':'#ff3b5c'};margin-top:4px">${s.avg_return_30d!=null?((s.avg_return_30d>=0?'+':'')+s.avg_return_30d.toFixed(1)+'%'):'—'}</div>
            <div class="dim" style="font-size:10px">30d return</div>
            <div class="dim" style="font-size:9px;margin-top:4px">n=${s.count} | ${(s.win_rate_14d||0).toFixed(0)}% win</div>
          </div>`).join('')}
        </div>
      </div>`;
    }
  }

  $('#content').innerHTML = html;
}

async function changePeriod(p) {
  btPeriod = p;
  $('#content').innerHTML = '<div style="padding:40px;text-align:center;color:#64748b">Recalculating...</div>';
  const bt = await apiCall(`/api/backtest?days=180&forward_period=${p}`);
  if (bt) appData.backtest = bt;
  renderBacktest();
}

// ─── Scan ───
async function triggerScan() {
  const btn = $('#scanBtn');
  if (btn) { btn.textContent = '⟳ Scanning...'; btn.style.opacity = '0.5'; }
  await apiPost('/api/scan', {});
  const poll = setInterval(async () => {
    const s = await apiCall('/api/scan/status');
    if (s && !s.running) {
      clearInterval(poll);
      if (btn) { btn.textContent = '✓ Complete'; btn.style.opacity = '1'; }
      const [stats, latest] = await Promise.all([apiCall('/api/stats'), apiCall('/api/scores/latest?limit=50')]);
      if (stats) appData.stats = stats;
      if (latest) appData.latest = latest;
      renderApp();
    }
  }, 3000);
}

// ─── Init ───
(async () => {
  const auth = await apiCall('/api/check-auth');
  if (auth && auth.authenticated) {
    await loadDashboard();
  } else {
    showLogin();
  }
})();
</script>
</body>
</html>
""".strip()


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    return DASHBOARD_HTML

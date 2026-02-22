# CyberScreener - Claude Code Guide

## Project Overview

**CyberScreener** is an automated investment intelligence platform that scans, scores, and backtests stocks across cybersecurity, energy, and defense sectors. It provides dual-scoring (long-term + options), backtesting, self-calibration, and options play generation via a FastAPI backend with an embedded HTML dashboard.

**Live at**: https://cyber.keltonshockey.com (SSL via Let's Encrypt, nginx reverse proxy)
**Auth**: Basic auth — `admin` / `cybershield2026`
**VPS**: DigitalOcean at `64.23.150.209`, code at `/opt/cyberscreener`
**Repo**: `sniffer9793/cyberscreener` on GitHub

---

## Project Structure

```
cyberscreener2/
├── Dockerfile
├── railway.toml
├── api/
│   ├── main.py              # FastAPI app + all endpoints (~860 lines)
│   ├── scheduler.py         # Scheduled scan daemon (every 2 hours)
│   ├── backfill.py          # Historical data bootstrapping
│   ├── requirements.txt
│   ├── dashboard_embed.html # Embedded frontend (single-file, ~51KB)
│   ├── core/
│   │   ├── scanner.py       # Score computation engine (~1,605 lines)
│   │   ├── universe.py      # Stock universe + sector definitions
│   │   └── timing.py        # Options timing intelligence
│   ├── db/
│   │   ├── models.py        # SQLite schema + ORM helpers
│   │   ├── migrate_timing.py
│   │   └── migrate_sectors.py
│   ├── backtest/
│   │   └── engine.py        # Quintile analysis, attribution, calibration (~508 lines)
│   └── intel/
│       ├── sec_filings.py   # SEC EDGAR + insider transactions
│       ├── sentiment.py     # Yahoo Finance news sentiment
│       └── earnings_calendar.py
└── scripts/
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI 0.115.6 + Uvicorn 0.34.0 |
| Language | Python 3.11 |
| Database | SQLite at `/data/db/cyberscreener.db` |
| Data Sources | yfinance, SEC EDGAR, Yahoo Finance |
| Data Processing | Pandas 2.0+, NumPy 1.24+ |
| Deployment | Docker + Railway.app |
| Frontend | Embedded single-file HTML5 dashboard |

---

## Local Development

```bash
cd api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Bootstrap 6 months of historical data (needed for backtesting)
python backfill.py --months 6

# Start API server
uvicorn main:app --reload --port 8000
```

## Production Deployment (DigitalOcean VPS)

**Deploy workflow**: Push to GitHub on Mac → SSH to VPS → `git pull` + `systemctl restart cyberscreener`

```bash
# On VPS: /opt/cyberscreener
git pull origin main
sudo systemctl restart cyberscreener
```

**Stack on VPS**: FastAPI (systemd service) + nginx reverse proxy + Let's Encrypt SSL (auto-renewing).

---

## Testing

No formal test suite. Validation approaches:
- `GET /health` — basic health check
- `POST /calibrate?dry_run=true` — test weight calibration without applying
- `GET /backtest/score-vs-returns?days=180` — validate scoring accuracy historically
- Manual endpoint testing via curl or the dashboard

---

## Key Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CYBERSCREENER_PASSWORD` | `cybershield2026` | Dashboard auth password |
| `DB_PATH` | `/app/data/cyberscreener.db` | SQLite database path |

## Current State (as of Feb 2026)

- **66 tickers** across cyber/energy/defense sectors
- **12-month backfill** in progress (6 months complete); re-calibrate after with `days=365`
- **Calibration ran**: Rule of 40 and Directional Conviction boosted; Discount Momentum and Asymmetry reduced
- **Intel layers**: SEC filings + Sentiment working; Whale flow only works on weekdays (needs live options chains)
- **Score history charts**: Flat lines expected — will populate as daily scans accumulate
- **Invalid Date chart bug**: Fixed; verify after next scan

## Dashboard (v3)

4 tabs:
- **Overview**: Summary view
- **Scores**: Ticker list with sector filters, LT + Opt score breakdowns, per-component bars, layer pills (SEC/Sentiment/Whale), score history chart, price/RSI chart
- **Plays**: Weight Tuner (sliders), Reality Check scoring (0-100, PASS/CAUTION/FAIL), fallback play generation (every ticker gets ≥1-2 plays), full risk/reward breakdown
- **Backtest**: Quintile analysis, layer attribution, earnings timing buckets

---

## Architecture Notes

### Scoring System

**Long-Term Score (0-100)** — "Would you hold this for 1-3 years?"
- Rule of 40 (25 pts), Relative Valuation (20 pts), FCF Margin (15 pts)
- Technical Trend (15 pts), Earnings Quality (10 pts), Discount+Momentum (15 pts)

**Options Score (0-100)** — "Is there an asymmetric short-term trade?"
- Earnings Catalyst (25 pts), IV Context (20 pts), Directional Conviction (20 pts)
- Technical Setup (15 pts), Liquidity (10 pts), Asymmetry (10 pts)

**Sector-specific weights** are defined in `api/core/universe.py` — different weight profiles for SaaS, Energy, REIT, and Defense stocks.

### Stock Universe (~90+ tickers)
- **Cybersecurity**: CRWD, PANW, FTNT, ZS, OKTA, CYBR, NET, S, DDOG, PLTR, and many more
- **Energy**: CCJ, CEG, FSLR, NEE, EQIX, DLR, etc.
- **Defense**: LMT, RTX, NOC, GD, AVAV, KTOS, etc.

### Database Schema (SQLite)
- `scans` — scan run metadata
- `scores` — per-ticker scores per scan (all components + technicals + fundamentals)
- `prices` — historical close prices
- `signals` — alert signals
- `score_weights` — calibration history

### Scheduler
Runs `scheduler.py --daemon` on Railway. Scans every 2 hours on weekdays during market hours (6 AM - 10 PM). Scan covers all tickers; results stored in SQLite.

---

## Important Files to Know

- `api/main.py` — All API endpoints; start here when adding new endpoints
- `api/core/scanner.py` — Core scoring logic; edit here for score calculation changes
- `api/core/universe.py` — Stock universe and sector weight profiles
- `api/db/models.py` — Database schema; add migration scripts for schema changes
- `api/dashboard_embed.html` — Single-file frontend; all UI lives here
- `api/backtest/engine.py` — Backtesting and calibration logic

---

## Common Tasks

### Adding a new ticker
Edit `api/core/universe.py` — add to appropriate sector list and assign sector profile.

### Adding a new API endpoint
Add to `api/main.py`. Follow existing patterns (auth via `verify_token` dependency, background tasks for long-running ops).

### Changing score weights
Use `POST /calibrate` to auto-adjust, or edit defaults in `api/core/scanner.py`. Weights are persisted in the `score_weights` table.

### Schema changes
Create a migration script in `api/db/` following the pattern in `migrate_sectors.py`, then update `models.py`.

### Dashboard changes
Edit `api/dashboard_embed.html` — it's a single self-contained file with inline CSS and JS.

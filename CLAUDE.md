# QUAEST.TECH — Claude Code Guide

## Project Overview

**QUAEST.TECH** is an investment intelligence platform with a 3D voxel world interface. Users explore a Roman city where each building contains a different section of the site — stock scoring, options plays, backtesting, and market overview. The backend scans, scores, and backtests stocks across cybersecurity, energy, defense, and broad market sectors.

**Live at**: https://cyber.keltonshockey.com (SSL via Let's Encrypt, nginx reverse proxy)
**World**: https://cyber.keltonshockey.com/world (3D voxel city)
**VPS**: DigitalOcean at `64.23.150.209`, code at `/opt/cyberscreener`
**Repo**: `sniffer9793/cyberscreener` on GitHub

---

## Project Structure

```
cyberscreener/
├── CLAUDE.md
├── README.md
├── Dockerfile
├── railway.toml              # Legacy (now on DigitalOcean)
├── api/
│   ├── main.py               # FastAPI app + all endpoints (~2,888 lines)
│   ├── scheduler.py           # Scheduled scan daemon (every 30 min)
│   ├── backfill.py            # Historical data bootstrapping
│   ├── requirements.txt
│   ├── core/
│   │   ├── scanner.py         # Score computation + play generation (~1,825 lines)
│   │   ├── universe.py        # Cybersecurity sector universe (~102 lines)
│   │   ├── broad_universe.py  # Broad market universe (~84 lines)
│   │   ├── augur_weights.py   # Persona-based weight profiles (~166 lines)
│   │   └── timing.py          # Options timing intelligence (~412 lines)
│   ├── db/
│   │   ├── models.py          # SQLite schema + ORM helpers (~1,058 lines)
│   │   └── migrate_*.py       # Various migration scripts
│   ├── backtest/
│   │   └── engine.py          # Quintile analysis, attribution, calibration (~568 lines)
│   └── intel/
│       ├── ai_analysis.py     # Claude API (Haiku) play analysis
│       ├── sec_filings.py     # SEC EDGAR + insider transactions
│       ├── sentiment.py       # FinBERT + keyword-bag sentiment
│       ├── earnings_calendar.py
│       ├── news_intel.py      # News intelligence
│       └── notifier.py        # Alert notifications
├── frontend/                  # React 19 + Vite 7 SPA
│   ├── src/
│   │   ├── App.jsx            # Root router + data loading (~180 lines)
│   │   ├── main.jsx
│   │   ├── api/
│   │   │   ├── client.js      # Fetch wrapper with JWT auth
│   │   │   └── endpoints.js   # All API endpoint functions
│   │   ├── auth/
│   │   │   ├── AuthContext.jsx    # JWT auth state management
│   │   │   ├── LoginPage.jsx
│   │   │   ├── RegisterPage.jsx
│   │   │   └── QuaestorCreator.jsx  # Character creation
│   │   ├── pages/
│   │   │   ├── BasilicaPage.jsx   # Overview: RSI chart, killer plays, leaders (~340 lines)
│   │   │   ├── ConvictionPage.jsx # Stock scores, breakdowns, intel layers (~368 lines)
│   │   │   ├── PactumPage.jsx     # Options plays, RC scoring, AI analysis (~673 lines)
│   │   │   ├── TickerPage.jsx     # Per-ticker deep dive: scores, charts, signals (~237 lines)
│   │   │   ├── ArchivePage.jsx    # Backtest, calibration, research (~263 lines)
│   │   │   └── WorldPage.jsx      # 3D voxel game + building panel integration (~275 lines)
│   │   ├── components/
│   │   │   ├── ui/            # Card, Badge, ScoreBar, BreakdownPanel, BuildingPanel, etc.
│   │   │   ├── charts/        # SvgAreaChart, SvgPriceChart, SvgBarChart, Interactive*, etc.
│   │   │   ├── layout/        # Header, NavBar, Footer, SearchBar
│   │   │   └── world/         # DistrictPanel
│   │   ├── game/
│   │   │   ├── VoxelGame.jsx      # React wrapper for Three.js world
│   │   │   ├── config.js          # Constants, building defs, brand colors
│   │   │   ├── entities/
│   │   │   │   └── NPCData.js     # NPC registry (dialogs, behaviors, sprites)
│   │   │   └── voxel/
│   │   │       ├── VoxelWorld.js       # Main scene orchestrator (~881 lines)
│   │   │       ├── VoxelMeshBuilder.js # Per-building mesh groups
│   │   │       ├── BuildingDecorator.js # Architectural features
│   │   │       ├── TextureAtlas.js     # Procedural 128x128 texture atlas
│   │   │       ├── SpriteGenerator.js  # Procedural Roman character sprites
│   │   │       ├── PlayerController.js # WASD movement, camera-relative
│   │   │       ├── VoxelNPC.js         # NPC patrol/wander/idle + dialog
│   │   │       └── CameraController.js # 3rd-person orbit, follow-cam
│   │   ├── hooks/             # useApi, useChartDimensions, usePolling
│   │   ├── theme/             # CSS variables, global styles, animations
│   │   └── utils/             # formatters, scoring helpers
│   ├── scripts/
│   │   └── generate-map.mjs   # Tiled-format JSON map generator
│   └── public/assets/maps/    # Generated roman-city.json
└── scripts/
    └── seed_earnings.py
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI 0.115.6 + Uvicorn 0.34.0 (Python 3.11) |
| Database | SQLite (WAL mode) at `/data/db/cyberscreener.db` |
| Frontend | React 19 + Vite 7 SPA |
| 3D Engine | Three.js (voxel renderer, procedural textures/sprites) |
| Data Sources | yfinance, SEC EDGAR, Yahoo Finance, HuggingFace FinBERT |
| AI | Claude API (Haiku) for options play analysis |
| Deployment | DigitalOcean VPS (systemd + nginx + Let's Encrypt) |

---

## Pages & Routes

| Route | Page | Description |
|-------|------|-------------|
| `/` | BasilicaPage | Market overview with interactive RSI chart, killer plays widget, sector leaders, momentum signals |
| `/conviction` | ConvictionPage | Full scoring table with LT/Opt breakdowns, intel layers, score history charts |
| `/pactum` | PactumPage | Options play generation with combined conviction sort, expandable RC explainers, AI analysis |
| `/ticker/:symbol` | TickerPage | Per-ticker deep dive: score summary, LT+Opt breakdowns, price chart, trend charts, signals |
| `/archive` | ArchivePage | Backtesting engine, quintile analysis, calibration, score-vs-returns research |
| `/world` | WorldPage | 3D Roman city where buildings contain site sections |

---

## The 3D World

The game world is a Roman city built with Three.js voxel rendering. Each building maps to a page:

| Building | Page | Content |
|----------|------|---------|
| **Basilica Julia** | Basilica | Market overview, killer plays, momentum, leaders |
| **The Curia** | Conviction | Long-term stock scores, breakdowns, intel layers |
| **The Subura** | Pactum | Options plays, RC scoring, AI analysis |
| **The Tabularium** | Archive | Backtesting, quintile analysis, calibration |

**Building entry**: Walking inside triggers a full-screen `BuildingPanel` overlay. Player can dismiss with ESC, click outside, or walk out.

### Key 3D Features
- 3rd-person orbit camera with auto-follow
- Procedural texture atlas (128x128 canvas, 8x8 grid, NearestFilter pixel art)
- Procedural character sprites (7 types: player, legionary, senator, merchant, scholar, guard, vendor)
- Sky dome, ground shadows, atmospheric fog, Mediterranean lighting
- Indoor/outdoor transitions (hide exterior walls/roof, zoom camera, dim lights)
- NPC behaviors (patrol, wander, idle with dialog system)

### Map Generation
Run `node frontend/scripts/generate-map.mjs` to regenerate the Tiled-format JSON map.

---

## Scoring System

### Long-Term Score (0-100) — "Would you hold this for 1-3 years?"
- Rule of 40 (25 pts), Relative Valuation (20 pts), FCF Margin (15 pts)
- Technical Trend (15 pts), Earnings Quality (10 pts), Discount+Momentum (15 pts)

### Options Score (0-100) — "Is there an asymmetric short-term trade?"
- Earnings Catalyst (25 pts), IV Context (20 pts), Directional Conviction (20 pts)
- Technical Setup (15 pts), Liquidity (10 pts), Asymmetry (10 pts)

### Reality Check (0-100) — "Is this play actually tradeable?"
Unified server-side scoring via `_compute_rc()` in main.py:
- Trade Quality (25 pts): risk/reward, bid-ask spread, breakeven distance
- Execution (20 pts): volume, open interest, DTE, IV percentile
- Score Alignment (20 pts): opt_score + lt_score thresholds, elite bonus for either ≥70
- IV Context (15 pts): buying at low IV or selling at high IV
- Catalyst (10 pts): earnings proximity, RSI extremes, BB squeeze, trend alignment
- Technical (10 pts): RSI zone alignment with play direction, stable trend bonus

### Combined Conviction Score
Used for killer plays and Pactum default sort: `opt_score * 0.6 + lt_score * 0.4`

### Sector-Specific Weights
Defined in `api/core/universe.py` and `api/core/broad_universe.py` — profiles for SaaS, Energy, REIT, Defense, Financial, etc.

---

## Key Backend Features

### NaN Safety (scanner.py)
All yfinance numeric data passes through `_safe_num()` and `_safe_int()` helpers that catch NaN, None, and inf values. Critical because yfinance returns NaN for volume/openInterest on illiquid options chains. Without this, `int(float('nan'))` crashes play generation.

### Response Caching (main.py)
- `/stats` endpoint: 60-second in-memory TTL cache
- `/scores/latest` endpoint: 30-second in-memory TTL cache
- `/market/indices`: background thread refresh every 5 minutes
- Play generation: per-ticker cache with configurable TTL

### Killer Plays (main.py `/killer-plays`)
Quality-gated algorithm:
1. Combined score must be ≥ 70th percentile of all scored tickers
2. Requires opt_score ≥ 45 OR lt_score ≥ 55
3. Quality gate: must have catalyst (earnings, RSI extreme, BB squeeze) OR strong scores (opt≥50 or lt≥60)
4. Assigns conviction tier: HIGH (≥55), SOLID (≥45), WATCH
5. Enriches with catalyst labels (earnings, oversold, overbought, demand signal, etc.)

### Play Enrichment (main.py)
Every generated play gets enriched with:
- `risk_reward_ratio`, `bid_ask_spread_pct`, `iv_percentile`
- `breakeven_distance_pct`, `rc_score`, `rc_breakdown`
- Whale flow data, earnings dates, AI analysis (Claude Haiku)

---

## Stock Universe (~490+ tickers)

- **Cybersecurity**: CRWD, PANW, FTNT, ZS, OKTA, CYBR, NET, S, DDOG, PLTR, etc.
- **Energy**: CCJ, CEG, FSLR, NEE, EQIX, DLR, etc.
- **Defense**: LMT, RTX, NOC, GD, AVAV, KTOS, etc.
- **Broad Market**: Tech, Finance, Health, Consumer, Industrials, REITs (~400+ tickers)

Scanner runs every 30 minutes via systemd scheduler service.

---

## Database Schema (SQLite, WAL mode)

- `scans` — scan run metadata
- `scores` — per-ticker scores per scan (all components + technicals + fundamentals)
- `prices` — historical close prices
- `signals` — alert signals
- `score_weights` — calibration history
- `watchlist` — user-added custom tickers
- `earnings_dates` — multi-source earnings calendar
- `options_plays` — play P&L tracking
- `users` — JWT auth with augur profiles
- `augur_profiles` — character attributes (prudentia, audacia, sapientia, etc.)
- `refresh_tokens` — JWT rotation

---

## Intel Layers

- **SEC Filings**: Insider transactions (Form 4), analyst recommendations, 8-K filing counts
- **Sentiment**: FinBERT via HuggingFace API (falls back to keyword-bag)
- **Earnings Calendar**: Multi-source (DB -> yfinance -> FMP API -> Yahoo scrape)
- **Whale Flow**: Unusual options activity detection from pre-fetched chains
- **AI Analysis**: Claude API (Haiku) for play quality assessment

---

## Local Development

```bash
# Backend
cd api
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev  # Vite dev server on :5173
```

## Production Deployment (DigitalOcean VPS)

**Deploy workflow**: Push to GitHub -> SSH to droplet -> pull + build + restart services

```bash
# Build frontend + push
cd frontend && npm run build && cd ..
git add -A && git commit -m "deploy" && git push origin main

# Deploy on droplet
ssh root@cyber.keltonshockey.com "cd /opt/cyberscreener && git pull && cd frontend && npm run build && cd .. && systemctl restart cyberscreener.service cyberscreener-scheduler.service"
```

**Services on VPS**:
- `cyberscreener.service` — FastAPI app via uvicorn
- `cyberscreener-scheduler.service` — 30-min scan loop
- nginx reverse proxy with Let's Encrypt SSL

---

## Testing

No formal test suite. Validation approaches:
- `GET /health` — basic health check
- `python3 -c "import py_compile; py_compile.compile('main.py')"` — syntax check
- `npm run build` — frontend compilation check
- `GET /backtest/score-vs-returns?days=180` — scoring accuracy validation
- Manual endpoint testing via curl or browser

---

## Common Tasks

### Adding a new ticker
Edit `api/core/universe.py` (cyber sector) or `api/core/broad_universe.py` (broad market) — add to appropriate sector list and assign scoring profile.

### Adding a new API endpoint
Add to `api/main.py`. Follow existing patterns (auth via JWT, background tasks for long-running ops).

### Changing score weights
Use `POST /calibrate` to auto-adjust, or edit defaults in `api/core/scanner.py`.

### Modifying the 3D world
- **Map layout**: Edit `frontend/scripts/generate-map.mjs`, run `node generate-map.mjs`
- **Building textures**: Edit `TextureAtlas.js` PAL colors or drawing functions
- **Character sprites**: Edit `SpriteGenerator.js` palettes or drawing
- **Building features**: Edit `BuildingDecorator.js`
- **Building defs**: Edit `frontend/src/game/config.js` BUILDING_DEFS
- **Camera/movement**: Edit `CameraController.js` or `PlayerController.js`
- **NPCs**: Edit `NPCData.js`

### Adding content to a building
Building panel system is in `WorldPage.jsx`. Each building ID maps to a page component:
```
basilica   -> <BasilicaPage />
curia      -> <ConvictionPage />
subura     -> <PactumPage />
tabularium -> <ArchivePage />
```
Edit `renderBuildingContent()` in WorldPage.jsx to change what content appears.

### Frontend build + deploy
```bash
cd frontend && npm run build
git add -A && git commit -m "deploy" && git push origin main
ssh root@cyber.keltonshockey.com "cd /opt/cyberscreener && git pull && cd frontend && npm run build && cd .. && systemctl restart cyberscreener.service cyberscreener-scheduler.service"
```

---

## Current State (as of March 2026)

- **~490+ tickers** across cyber/energy/defense/tech/health/finance/REIT/consumer/industrial sectors
- **6 pages**: Basilica, Conviction, Pactum, Ticker Summary, Archive, World
- **Interactive RSI chart** on Basilica with clickable bars navigating to ticker pages
- **Killer plays** with combined conviction scoring and quality gates
- **Pactum** with combined conviction sort, expandable RC explainers per play
- **Ticker page** (`/ticker/:symbol`) with score summaries, breakdowns, charts, signals
- **Unified RC scoring** computed server-side with 6 components (100pts total)
- **NaN-safe** options chain processing prevents crashes on illiquid tickers
- **Response caching** on /stats (60s) and /scores/latest (30s) for fast page loads
- **3D voxel world** with 4 buildings, each containing a page's content
- **No formal test suite** — biggest risk for refactoring

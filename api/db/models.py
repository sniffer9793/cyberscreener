"""
Database models — SQLite schema + data access layer.
Tables: scans, scores, prices, signals, score_weights (NEW: for self-calibration)
"""

import sqlite3
import os
import json
from datetime import datetime, timedelta

DB_PATH = os.environ.get("CYBERSCREENER_DB", "/app/data/cyberscreener.db")

def get_db():
    """Get a database connection with row factory."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _migrate_scores_table(conn):
    """Add v2 columns to existing scores table if they don't exist."""
    # Get existing columns
    try:
        cursor = conn.execute("PRAGMA table_info(scores)")
        existing_cols = {row[1] for row in cursor.fetchall()}
    except Exception:
        return  # Table doesn't exist yet, CREATE TABLE will handle it

    if not existing_cols:
        return

    # New v2 columns to add
    new_columns = [
        ("lt_rule_of_40", "REAL"),
        ("lt_valuation", "REAL"),
        ("lt_fcf_margin", "REAL"),
        ("lt_trend", "REAL"),
        ("lt_earnings_quality", "REAL"),
        ("lt_discount_momentum", "REAL"),
        ("opt_earnings_catalyst", "REAL"),
        ("opt_iv_context", "REAL"),
        ("opt_directional", "REAL"),
        ("opt_technical", "REAL"),
        ("opt_liquidity", "REAL"),
        ("opt_asymmetry", "REAL"),
        ("operating_margin_pct", "REAL"),
        ("ev_revenue", "REAL"),
        ("fcf_margin_pct", "REAL"),
        ("revenue_b", "REAL"),
        ("iv_rank", "REAL"),
        ("perf_1m", "REAL"),
        ("lt_breakdown", "TEXT"),
        ("opt_breakdown", "TEXT"),
    ]

    for col_name, col_type in new_columns:
        if col_name not in existing_cols:
            try:
                conn.execute(f"ALTER TABLE scores ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass  # Column might already exist from a partial migration

    conn.commit()


def init_db():
    """Initialize all tables + migrate schema if needed."""
    conn = get_db()

    # ── Schema migration: add new v2 columns to existing scores table ──
    _migrate_scores_table(conn)

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            tickers_scanned INTEGER DEFAULT 0,
            duration_seconds REAL,
            config_json TEXT,
            intel_layers TEXT DEFAULT 'base'
        );

        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            price REAL,
            market_cap_b REAL,

            -- Composite scores
            lt_score REAL DEFAULT 0,
            opt_score REAL DEFAULT 0,

            -- LT score components (v2)
            lt_rule_of_40 REAL,
            lt_valuation REAL,
            lt_fcf_margin REAL,
            lt_trend REAL,
            lt_earnings_quality REAL,
            lt_discount_momentum REAL,

            -- Opt score components (v2)
            opt_earnings_catalyst REAL,
            opt_iv_context REAL,
            opt_directional REAL,
            opt_technical REAL,
            opt_liquidity REAL,
            opt_asymmetry REAL,

            -- Raw fundamentals
            revenue_growth_pct REAL,
            gross_margin_pct REAL,
            operating_margin_pct REAL,
            ps_ratio REAL,
            pe_ratio REAL,
            ev_revenue REAL,
            fcf_m REAL,
            fcf_margin_pct REAL,
            revenue_b REAL,

            -- Raw technicals
            rsi REAL,
            sma_20 REAL,
            sma_50 REAL,
            sma_200 REAL,
            bb_width REAL,
            vol_ratio REAL,
            iv_30d REAL,
            iv_rank REAL,
            beta REAL,
            short_pct REAL,

            -- Performance
            perf_1y REAL,
            perf_3m REAL,
            perf_1m REAL,
            pct_from_52w_high REAL,
            days_to_earnings INTEGER,

            -- Intelligence layer scores
            sec_score REAL DEFAULT 0,
            sentiment_score REAL DEFAULT 0,
            sentiment_bull_pct REAL,
            whale_score REAL DEFAULT 0,
            pc_ratio REAL,
            insider_buys_30d INTEGER DEFAULT 0,
            insider_sells_30d INTEGER DEFAULT 0,

            -- LT score component breakdown (JSON for dashboard)
            lt_breakdown TEXT,
            opt_breakdown TEXT,

            FOREIGN KEY (scan_id) REFERENCES scans(id)
        );

        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            close_price REAL NOT NULL,
            UNIQUE(ticker, date)
        );

        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER,
            ticker TEXT NOT NULL,
            signal_type TEXT,
            signal_text TEXT,
            impact TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scan_id) REFERENCES scans(id)
        );

        -- NEW: Score weight history for self-calibration
        CREATE TABLE IF NOT EXISTS score_weights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            score_type TEXT NOT NULL,  -- 'lt' or 'opt'
            weights_json TEXT NOT NULL,  -- JSON dict of component -> weight
            backtest_correlation REAL,   -- overall score-return correlation
            backtest_quintile_spread REAL,  -- Q5 avg return - Q1 avg return
            data_points INTEGER,
            notes TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_scores_scan ON scores(scan_id);
        CREATE INDEX IF NOT EXISTS idx_scores_ticker ON scores(ticker);
        CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON prices(ticker, date);
        CREATE INDEX IF NOT EXISTS idx_signals_scan ON signals(scan_id);
    """)

    conn.commit()
    conn.close()


def save_scan(results, intel_layers=None, duration_seconds=None):
    """Save a complete scan to the database. Returns scan_id."""
    conn = get_db()

    layers_str = ",".join(intel_layers) if intel_layers else "base"
    cursor = conn.execute(
        "INSERT INTO scans (timestamp, tickers_scanned, duration_seconds, intel_layers) VALUES (?, ?, ?, ?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), len(results), duration_seconds, layers_str)
    )
    scan_id = cursor.lastrowid

    for r in results:
        # Save score record
        lt_breakdown = json.dumps(r.get("lt_breakdown", {}))
        opt_breakdown = json.dumps(r.get("opt_breakdown", {}))

        conn.execute("""
            INSERT INTO scores (
                scan_id, ticker, price, market_cap_b,
                lt_score, opt_score,
                lt_rule_of_40, lt_valuation, lt_fcf_margin, lt_trend, lt_earnings_quality, lt_discount_momentum,
                opt_earnings_catalyst, opt_iv_context, opt_directional, opt_technical, opt_liquidity, opt_asymmetry,
                revenue_growth_pct, gross_margin_pct, operating_margin_pct,
                ps_ratio, pe_ratio, ev_revenue, fcf_m, fcf_margin_pct, revenue_b,
                rsi, sma_20, sma_50, sma_200, bb_width, vol_ratio, iv_30d, iv_rank, beta, short_pct,
                perf_1y, perf_3m, perf_1m, pct_from_52w_high, days_to_earnings,
                sec_score, sentiment_score, sentiment_bull_pct, whale_score, pc_ratio,
                insider_buys_30d, insider_sells_30d,
                lt_breakdown, opt_breakdown
            ) VALUES (
                ?,?,?,?,
                ?,?,
                ?,?,?,?,?,?,
                ?,?,?,?,?,?,
                ?,?,?,
                ?,?,?,?,?,?,
                ?,?,?,?,?,?,?,?,?,?,
                ?,?,?,?,?,
                ?,?,?,?,?,
                ?,?,
                ?,?
            )
        """, (
            scan_id, r["ticker"], r.get("price"), r.get("market_cap_b"),
            r.get("lt_score", 0), r.get("opt_score", 0),
            r.get("lt_rule_of_40"), r.get("lt_valuation"), r.get("lt_fcf_margin"),
            r.get("lt_trend"), r.get("lt_earnings_quality"), r.get("lt_discount_momentum"),
            r.get("opt_earnings_catalyst"), r.get("opt_iv_context"), r.get("opt_directional"),
            r.get("opt_technical"), r.get("opt_liquidity"), r.get("opt_asymmetry"),
            r.get("revenue_growth_pct"), r.get("gross_margin_pct"), r.get("operating_margin_pct"),
            r.get("ps_ratio"), r.get("pe_ratio"), r.get("ev_revenue"),
            r.get("fcf_m"), r.get("fcf_margin_pct"), r.get("revenue_b"),
            r.get("rsi"), r.get("sma_20"), r.get("sma_50"), r.get("sma_200"),
            r.get("bb_width"), r.get("vol_ratio"), r.get("iv_30d"), r.get("iv_rank"),
            r.get("beta"), r.get("short_pct"),
            r.get("perf_1y"), r.get("perf_3m"), r.get("perf_1m"),
            r.get("pct_from_52w_high"), r.get("days_to_earnings"),
            r.get("sec_score", 0), r.get("sentiment_score", 0), r.get("sentiment_bull_pct"),
            r.get("whale_score", 0), r.get("pc_ratio"),
            r.get("insider_buys_30d", 0), r.get("insider_sells_30d", 0),
            lt_breakdown, opt_breakdown,
        ))

        # Save price snapshot
        today_str = datetime.now().strftime("%Y-%m-%d")
        if r.get("price"):
            conn.execute(
                "INSERT OR IGNORE INTO prices (ticker, date, close_price) VALUES (?, ?, ?)",
                (r["ticker"], today_str, r["price"])
            )

        # Save signals
        for reason in r.get("lt_reasons", []) + r.get("opt_reasons", []):
            impact = "positive" if any(e in reason for e in ["🚀", "💎", "💰", "🎯", "🌋"]) else \
                     "negative" if any(e in reason for e in ["⚠️", "🔴", "💸"]) else "neutral"
            conn.execute(
                "INSERT INTO signals (scan_id, ticker, signal_type, signal_text, impact) VALUES (?, ?, ?, ?, ?)",
                (scan_id, r["ticker"], "score", reason, impact)
            )

    conn.commit()
    conn.close()
    return scan_id


def get_score_history(ticker, days=90):
    """Get historical scores for a ticker."""
    conn = get_db()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT s.*, sc.timestamp as scan_date
        FROM scores s
        JOIN scans sc ON s.scan_id = sc.id
        WHERE s.ticker = ? AND sc.timestamp >= ?
        ORDER BY sc.timestamp ASC
    """, (ticker, cutoff)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_scores_for_backtest(days=180):
    """Get all score records with timestamps for backtesting."""
    conn = get_db()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT s.*, sc.timestamp as scan_date
        FROM scores s
        JOIN scans sc ON s.scan_id = sc.id
        WHERE sc.timestamp >= ?
        ORDER BY sc.timestamp ASC
    """, (cutoff,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_price(ticker, date_str):
    """Get a specific price snapshot. Returns float or None."""
    conn = get_db()
    row = conn.execute(
        "SELECT close_price FROM prices WHERE ticker = ? AND date = ?",
        (ticker, date_str)
    ).fetchone()
    conn.close()
    return row["close_price"] if row else None


def get_nearest_price(ticker, target_date_str, window_days=5):
    """Get the nearest price to a target date within a window."""
    conn = get_db()
    target = datetime.strptime(target_date_str, "%Y-%m-%d")
    start = (target - timedelta(days=window_days)).strftime("%Y-%m-%d")
    end = (target + timedelta(days=window_days)).strftime("%Y-%m-%d")

    row = conn.execute("""
        SELECT close_price, date,
               ABS(julianday(date) - julianday(?)) as day_diff
        FROM prices
        WHERE ticker = ? AND date BETWEEN ? AND ?
        ORDER BY day_diff ASC LIMIT 1
    """, (target_date_str, ticker, start, end)).fetchone()
    conn.close()
    return row["close_price"] if row else None


def save_score_weights(score_type, weights, correlation=None, quintile_spread=None, data_points=None, notes=None):
    """Save a weight configuration for self-calibration tracking."""
    conn = get_db()
    conn.execute("""
        INSERT INTO score_weights (timestamp, score_type, weights_json, backtest_correlation, backtest_quintile_spread, data_points, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        score_type,
        json.dumps(weights),
        correlation,
        quintile_spread,
        data_points,
        notes,
    ))
    conn.commit()
    conn.close()


def get_latest_weights(score_type):
    """Get the most recent weight configuration."""
    conn = get_db()
    row = conn.execute("""
        SELECT * FROM score_weights
        WHERE score_type = ?
        ORDER BY id DESC LIMIT 1
    """, (score_type,)).fetchone()
    conn.close()
    if row:
        result = dict(row)
        result["weights"] = json.loads(result["weights_json"])
        return result
    return None


def get_scan_count():
    """Get total number of scans."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
    conn.close()
    return count

# Backward-compatible alias
get_price_on_date = get_nearest_price

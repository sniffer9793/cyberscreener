"""
Database models and schema for CyberScreener historical tracking.

Tables:
- scans: Each full scan run (timestamp, config, summary)
- scores: Per-ticker scores per scan (lt_score, opt_score, sub-scores)
- signals: Individual signals detected per ticker per scan
- prices: Daily price snapshots for return calculations
- backtest_results: Cached backtest analysis results
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).parent / "cyberscreener.db")))


def get_db():
    """Get a database connection with WAL mode for concurrent reads."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            tickers_scanned INTEGER NOT NULL,
            config_json TEXT,
            duration_seconds REAL,
            intel_layers TEXT  -- comma-separated: 'sec,sentiment,whale'
        );

        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL REFERENCES scans(id),
            ticker TEXT NOT NULL,
            price REAL,
            market_cap_b REAL,

            -- Core scores
            lt_score INTEGER NOT NULL DEFAULT 0,
            opt_score INTEGER NOT NULL DEFAULT 0,

            -- Fundamental components
            revenue_growth_pct REAL,
            gross_margin_pct REAL,
            ps_ratio REAL,
            pe_ratio REAL,
            fcf_m REAL,

            -- Technical components
            rsi REAL,
            sma_20 REAL,
            sma_50 REAL,
            sma_200 REAL,
            bb_width REAL,
            vol_ratio REAL,
            iv_30d REAL,
            beta REAL,
            short_pct REAL,

            -- Performance
            perf_1y REAL,
            perf_3m REAL,
            pct_from_52w_high REAL,

            -- Earnings
            days_to_earnings INTEGER,

            -- Intelligence sub-scores (for backtest attribution)
            sec_score INTEGER DEFAULT 0,
            sentiment_score INTEGER DEFAULT 0,
            sentiment_bull_pct REAL,
            whale_score INTEGER DEFAULT 0,
            pc_ratio REAL,

            -- Insider activity
            insider_buys_30d INTEGER DEFAULT 0,
            insider_sells_30d INTEGER DEFAULT 0,

            UNIQUE(scan_id, ticker)
        );

        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL REFERENCES scans(id),
            ticker TEXT NOT NULL,
            signal_type TEXT NOT NULL,  -- 'fundamental', 'technical', 'sec', 'sentiment', 'whale'
            signal_text TEXT NOT NULL,
            impact TEXT,  -- 'bullish', 'bearish', 'neutral'
            score_contribution INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            close_price REAL NOT NULL,
            volume REAL,
            UNIQUE(ticker, date)
        );

        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            analysis_type TEXT NOT NULL,  -- 'score_vs_returns', 'layer_attribution', 'earnings_timing'
            params_json TEXT,
            results_json TEXT NOT NULL
        );

        -- Indexes for fast queries
        CREATE INDEX IF NOT EXISTS idx_scores_ticker ON scores(ticker);
        CREATE INDEX IF NOT EXISTS idx_scores_scan ON scores(scan_id);
        CREATE INDEX IF NOT EXISTS idx_scores_ticker_scan ON scores(ticker, scan_id);
        CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker, scan_id);
        CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON prices(ticker, date);
        CREATE INDEX IF NOT EXISTS idx_scans_timestamp ON scans(timestamp);
    """)
    conn.commit()
    conn.close()


def save_scan(results, intel_layers=None, duration_seconds=None, config=None):
    """Save a complete scan to the database. Returns scan_id."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO scans (tickers_scanned, config_json, duration_seconds, intel_layers) VALUES (?, ?, ?, ?)",
            (len(results), json.dumps(config) if config else None,
             duration_seconds, ",".join(intel_layers) if intel_layers else None)
        )
        scan_id = cursor.lastrowid

        for r in results:
            # Insert score row
            conn.execute("""
                INSERT INTO scores (
                    scan_id, ticker, price, market_cap_b,
                    lt_score, opt_score,
                    revenue_growth_pct, gross_margin_pct, ps_ratio, pe_ratio, fcf_m,
                    rsi, sma_20, sma_50, sma_200, bb_width, vol_ratio, iv_30d, beta, short_pct,
                    perf_1y, perf_3m, pct_from_52w_high,
                    days_to_earnings,
                    sec_score, sentiment_score, sentiment_bull_pct, whale_score, pc_ratio,
                    insider_buys_30d, insider_sells_30d
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                scan_id, r["ticker"], r.get("price"), r.get("market_cap_b"),
                r.get("lt_score", 0), r.get("opt_score", 0),
                r.get("revenue_growth_pct"), r.get("gross_margin_pct"),
                r.get("ps_ratio"), r.get("pe_ratio"), r.get("fcf_m"),
                r.get("rsi"), r.get("sma_20"), r.get("sma_50"), r.get("sma_200"),
                r.get("bb_width"), r.get("vol_ratio"), r.get("iv_30d"),
                r.get("beta"), r.get("short_pct"),
                r.get("perf_1y"), r.get("perf_3m"), r.get("pct_from_52w_high"),
                r.get("days_to_earnings"),
                r.get("sec_intel", {}).get("score", 0) if r.get("sec_intel") else 0,
                r.get("sentiment", {}).get("score", 0) if r.get("sentiment") else 0,
                r.get("sentiment", {}).get("combined_bull_pct") if r.get("sentiment") else None,
                r.get("whale_flow", {}).get("score", 0) if r.get("whale_flow") else 0,
                r.get("whale_flow", {}).get("pc_ratio") if r.get("whale_flow") else None,
                r.get("sec_intel", {}).get("insider_buys", 0) if r.get("sec_intel") else 0,
                r.get("sec_intel", {}).get("insider_sells", 0) if r.get("sec_intel") else 0,
            ))

            # Insert signal rows
            for reason in r.get("lt_reasons", []):
                impact = "bullish" if any(e in reason for e in ["🟢", "🚀", "💎", "💰", "💵", "🏷"]) else \
                         "bearish" if any(e in reason for e in ["🔴", "⚠️", "💸"]) else "neutral"
                conn.execute(
                    "INSERT INTO signals (scan_id, ticker, signal_type, signal_text, impact) VALUES (?, ?, ?, ?, ?)",
                    (scan_id, r["ticker"], "fundamental", reason, impact)
                )

            # Save current price snapshot
            today = datetime.now().strftime("%Y-%m-%d")
            if r.get("price"):
                conn.execute(
                    "INSERT OR IGNORE INTO prices (ticker, date, close_price) VALUES (?, ?, ?)",
                    (r["ticker"], today, r["price"])
                )

        conn.commit()
        return scan_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_score_history(ticker, days=90):
    """Get historical scores for a ticker."""
    conn = get_db()
    rows = conn.execute("""
        SELECT s.timestamp, sc.lt_score, sc.opt_score, sc.price,
               sc.sec_score, sc.sentiment_score, sc.whale_score,
               sc.rsi, sc.iv_30d, sc.days_to_earnings
        FROM scores sc
        JOIN scans s ON sc.scan_id = s.id
        WHERE sc.ticker = ?
        AND s.timestamp >= datetime('now', ?)
        ORDER BY s.timestamp ASC
    """, (ticker, f"-{days} days")).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_scores_for_backtest(days=180):
    """Get all scores with forward returns for backtesting."""
    conn = get_db()
    rows = conn.execute("""
        SELECT
            sc.ticker,
            s.timestamp as scan_date,
            sc.price as entry_price,
            sc.lt_score,
            sc.opt_score,
            sc.sec_score,
            sc.sentiment_score,
            sc.sentiment_bull_pct,
            sc.whale_score,
            sc.pc_ratio,
            sc.rsi,
            sc.iv_30d,
            sc.days_to_earnings,
            sc.revenue_growth_pct,
            sc.gross_margin_pct,
            sc.ps_ratio,
            sc.insider_buys_30d,
            sc.insider_sells_30d
        FROM scores sc
        JOIN scans s ON sc.scan_id = s.id
        WHERE s.timestamp >= datetime('now', ?)
        ORDER BY s.timestamp ASC
    """, (f"-{days} days",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_price_on_date(ticker, date_str):
    """Get closing price for a ticker on or near a given date."""
    conn = get_db()
    # Try exact date, then within 3 days after
    row = conn.execute("""
        SELECT close_price, date FROM prices
        WHERE ticker = ? AND date >= ? AND date <= date(?, '+3 days')
        ORDER BY date ASC LIMIT 1
    """, (ticker, date_str, date_str)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_scan_count():
    """Get total number of scans in the database."""
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) as cnt FROM scans").fetchone()
    conn.close()
    return row["cnt"]


# Initialize on import
init_db()

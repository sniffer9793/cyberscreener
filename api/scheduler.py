"""
Scheduler — runs scans on a schedule and saves to DB.

Usage:
  python scheduler.py                  # Run once now
  python scheduler.py --daemon         # Run on schedule (weekdays at market close)
  python scheduler.py --interval 3600  # Run every N seconds
"""

import sys
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.scanner import run_scan, ALL_TICKERS
from db.models import init_db, save_scan, get_scan_count

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scanner.log"),
    ]
)
logger = logging.getLogger(__name__)


def run_scheduled_scan():
    """Execute a full scan and save results to database."""
    logger.info(f"Starting scan of {len(ALL_TICKERS)} tickers...")
    start = time.time()

    def log_progress(ticker, i, total):
        if (i + 1) % 5 == 0 or i == 0:
            logger.info(f"  Scanning {ticker} ({i+1}/{total})")

    results = run_scan(callback=log_progress)
    duration = time.time() - start

    if results:
        scan_id = save_scan(
            results,
            intel_layers=["sec"],
            duration_seconds=duration,
            config={"mode": "scheduled", "tickers": len(ALL_TICKERS)},
        )
        logger.info(f"✅ Scan #{scan_id} complete: {len(results)} tickers in {duration:.1f}s "
                     f"(total scans in DB: {get_scan_count()})")
    else:
        logger.error("❌ Scan failed — no results returned.")


def is_market_hours():
    """Check if we're in a reasonable window for scanning (weekday, not too early/late)."""
    now = datetime.now()
    # Skip weekends
    if now.weekday() >= 5:
        return False
    # Only scan between 6 AM and 10 PM
    if now.hour < 6 or now.hour > 22:
        return False
    return True


def daemon_loop(interval_seconds=3600):
    """Run scans on a loop."""
    logger.info(f"Starting scheduler daemon (interval: {interval_seconds}s)")
    logger.info(f"Tracking {len(ALL_TICKERS)} tickers")

    while True:
        try:
            if is_market_hours():
                run_scheduled_scan()
            else:
                logger.info("Outside market hours, skipping scan.")
        except Exception as e:
            logger.error(f"Scan error: {e}")

        logger.info(f"Next scan in {interval_seconds}s...")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CyberScreener Scheduler")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode")
    parser.add_argument("--interval", type=int, default=3600, help="Seconds between scans (default: 3600)")
    args = parser.parse_args()

    init_db()

    if args.daemon:
        daemon_loop(args.interval)
    else:
        run_scheduled_scan()

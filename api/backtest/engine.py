"""
Backtest Engine v2 — Uses stored prices from DB only (no yfinance calls).

Analyses:
1. Score vs Returns (quintile analysis): Did high scores predict high returns?
2. Component Attribution: Which score components best predicted returns?
3. Earnings Timing: Optimal entry window relative to earnings dates?
4. Self-Calibration: Auto-adjust scoring weights based on what actually predicted returns.
"""

import json
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from db.models import get_db, get_all_scores_for_backtest, get_nearest_price, save_score_weights, get_latest_weights


def _get_forward_return(ticker, score_date_str, forward_days):
    """
    Calculate forward return for a ticker from a specific date.
    Uses stored prices from DB — no external API calls.
    """
    entry_price = get_nearest_price(ticker, score_date_str, window_days=3)
    if not entry_price:
        return None

    target_date = datetime.strptime(score_date_str, "%Y-%m-%d") + timedelta(days=forward_days)
    exit_price = get_nearest_price(ticker, target_date.strftime("%Y-%m-%d"), window_days=5)
    if not exit_price:
        return None

    return round(((exit_price / entry_price) - 1) * 100, 2)


def _build_score_return_pairs(days=180, forward_period=30, score_field="lt_score"):
    """Build a list of (score, forward_return) pairs from stored data."""
    scores = get_all_scores_for_backtest(days)
    if not scores:
        return []

    pairs = []
    for s in scores:
        score_val = s.get(score_field)
        if score_val is None:
            continue

        scan_date = s.get("scan_date", "")
        if not scan_date:
            continue

        # Parse date from timestamp
        try:
            date_str = scan_date[:10]  # "YYYY-MM-DD" from "YYYY-MM-DD HH:MM:SS"
        except Exception:
            continue

        fwd_return = _get_forward_return(s["ticker"], date_str, forward_period)
        if fwd_return is not None:
            pairs.append({
                "ticker": s["ticker"],
                "date": date_str,
                "score": score_val,
                "forward_return": fwd_return,
                "record": s,
            })

    return pairs


def backtest_score_vs_returns(days=180, forward_period=30):
    """
    Q1: Did scores predict actual returns?
    Sorts all score records into quintiles, measures average forward return per quintile.
    """
    result = {
        "lt_analysis": _quintile_analysis(days, forward_period, "lt_score"),
        "opt_analysis": _quintile_analysis(days, forward_period, "opt_score"),
        "forward_period_days": forward_period,
        "lookback_days": days,
        "timestamp": datetime.now().isoformat(),
    }
    return result


def _quintile_analysis(days, forward_period, score_field):
    """Run quintile analysis for a specific score type."""
    pairs = _build_score_return_pairs(days, forward_period, score_field)

    if len(pairs) < 10:
        return {
            "status": "insufficient_data",
            "data_points": len(pairs),
            "message": f"Need at least 10 data points, have {len(pairs)}. Run more scans or backfill first.",
        }

    # Sort by score and divide into quintiles
    pairs.sort(key=lambda x: x["score"])
    n = len(pairs)
    quintile_size = n // 5

    quintiles = {}
    for q in range(5):
        start = q * quintile_size
        end = (q + 1) * quintile_size if q < 4 else n
        bucket = pairs[start:end]

        scores = [p["score"] for p in bucket]
        returns = [p["forward_return"] for p in bucket]

        quintiles[f"Q{q+1}"] = {
            "avg_score": round(np.mean(scores), 1),
            "min_score": round(min(scores), 1),
            "max_score": round(max(scores), 1),
            "avg_return": round(np.mean(returns), 2),
            "median_return": round(np.median(returns), 2),
            "win_rate": round(sum(1 for r in returns if r > 0) / len(returns) * 100, 1),
            "count": len(bucket),
        }

    # Overall correlation
    all_scores = [p["score"] for p in pairs]
    all_returns = [p["forward_return"] for p in pairs]

    correlation = round(float(np.corrcoef(all_scores, all_returns)[0, 1]), 3) if len(pairs) > 2 else 0

    # Quintile spread: Q5 return - Q1 return
    q5_return = quintiles["Q5"]["avg_return"]
    q1_return = quintiles["Q1"]["avg_return"]
    quintile_spread = round(q5_return - q1_return, 2)

    # Is the score monotonically increasing? (ideal)
    quintile_returns = [quintiles[f"Q{q+1}"]["avg_return"] for q in range(5)]
    monotonic_violations = sum(1 for i in range(4) if quintile_returns[i+1] < quintile_returns[i])

    return {
        "status": "ok",
        "score_type": score_field,
        "data_points": len(pairs),
        "correlation": correlation,
        "quintile_spread": quintile_spread,
        "monotonic_violations": monotonic_violations,
        "is_predictive": correlation > 0.05 and quintile_spread > 1.0,
        "quintiles": quintiles,
        "interpretation": _interpret_quintile(correlation, quintile_spread, monotonic_violations),
    }


def _interpret_quintile(correlation, spread, violations):
    """Human-readable interpretation of backtest results."""
    parts = []
    if correlation > 0.15:
        parts.append(f"Strong positive correlation ({correlation:.3f}) — scores predict returns well.")
    elif correlation > 0.05:
        parts.append(f"Moderate positive correlation ({correlation:.3f}) — scores have some predictive power.")
    elif correlation > -0.05:
        parts.append(f"Weak/no correlation ({correlation:.3f}) — scores don't reliably predict returns.")
    else:
        parts.append(f"Negative correlation ({correlation:.3f}) — scores are inversely related to returns. Scoring needs revision.")

    if spread > 5:
        parts.append(f"Q5 outperformed Q1 by {spread:.1f}% — significant spread.")
    elif spread > 1:
        parts.append(f"Q5 outperformed Q1 by {spread:.1f}% — modest but positive spread.")
    else:
        parts.append(f"Q5-Q1 spread is only {spread:.1f}% — not meaningful.")

    if violations == 0:
        parts.append("Perfectly monotonic: higher scores = higher returns across all quintiles.")
    elif violations <= 1:
        parts.append(f"Mostly monotonic ({violations} violation) — generally higher scores = higher returns.")
    else:
        parts.append(f"Non-monotonic ({violations} violations) — score-return relationship is noisy.")

    return " ".join(parts)


def backtest_layer_attribution(days=180, forward_period=30):
    """
    Q2: Which score components contributed most to predicting returns?
    Measures correlation of each component with forward returns.
    """
    pairs = _build_score_return_pairs(days, forward_period, "lt_score")
    if len(pairs) < 10:
        return {"status": "insufficient_data", "data_points": len(pairs)}

    # LT score components
    lt_components = ["lt_rule_of_40", "lt_valuation", "lt_fcf_margin",
                     "lt_trend", "lt_earnings_quality", "lt_discount_momentum"]

    lt_attribution = {}
    for comp in lt_components:
        comp_scores = []
        returns = []
        for p in pairs:
            val = p["record"].get(comp)
            if val is not None:
                comp_scores.append(val)
                returns.append(p["forward_return"])

        if len(comp_scores) > 5:
            corr = float(np.corrcoef(comp_scores, returns)[0, 1])
            if np.isnan(corr):
                corr = 0
            lt_attribution[comp] = {
                "correlation": round(corr, 3),
                "avg_value": round(np.mean(comp_scores), 1),
                "data_points": len(comp_scores),
                "predictive": abs(corr) > 0.05,
            }

    # Options score components
    opt_pairs = _build_score_return_pairs(days, forward_period, "opt_score")
    opt_components = ["opt_earnings_catalyst", "opt_iv_context", "opt_directional",
                      "opt_technical", "opt_liquidity", "opt_asymmetry"]

    opt_attribution = {}
    for comp in opt_components:
        comp_scores = []
        returns = []
        for p in opt_pairs:
            val = p["record"].get(comp)
            if val is not None:
                comp_scores.append(val)
                returns.append(p["forward_return"])

        if len(comp_scores) > 5:
            corr = float(np.corrcoef(comp_scores, returns)[0, 1])
            if np.isnan(corr):
                corr = 0
            opt_attribution[comp] = {
                "correlation": round(corr, 3),
                "avg_value": round(np.mean(comp_scores), 1),
                "data_points": len(comp_scores),
                "predictive": abs(corr) > 0.05,
            }

    # Also measure raw indicator correlations
    raw_indicators = ["revenue_growth_pct", "gross_margin_pct", "ps_ratio", "pe_ratio",
                      "fcf_m", "rsi", "bb_width", "vol_ratio", "iv_30d", "beta", "short_pct",
                      "perf_3m", "pct_from_52w_high"]

    indicator_correlations = {}
    for ind in raw_indicators:
        vals = []
        rets = []
        for p in pairs:
            v = p["record"].get(ind)
            if v is not None:
                vals.append(v)
                rets.append(p["forward_return"])
        if len(vals) > 5:
            corr = float(np.corrcoef(vals, rets)[0, 1])
            if not np.isnan(corr):
                indicator_correlations[ind] = round(corr, 3)

    return {
        "status": "ok",
        "forward_period_days": forward_period,
        "lookback_days": days,
        "lt_component_attribution": lt_attribution,
        "opt_component_attribution": opt_attribution,
        "raw_indicator_correlations": indicator_correlations,
        "data_points": len(pairs),
        "timestamp": datetime.now().isoformat(),
    }


def backtest_earnings_timing(days=180):
    """
    Q3: What's the optimal entry window relative to earnings?
    Groups scores by days-to-earnings bucket and measures forward returns.
    """
    pairs_14d = _build_score_return_pairs(days, 14, "opt_score")
    pairs_30d = _build_score_return_pairs(days, 30, "opt_score")

    def _analyze_by_earnings_window(pairs, forward_label):
        buckets = {
            "1-4d pre": [],
            "5-14d pre": [],
            "15-30d pre": [],
            "30+d or no earnings": [],
        }

        for p in pairs:
            dte = p["record"].get("days_to_earnings")
            if dte is not None and 1 <= dte <= 4:
                buckets["1-4d pre"].append(p)
            elif dte is not None and 5 <= dte <= 14:
                buckets["5-14d pre"].append(p)
            elif dte is not None and 15 <= dte <= 30:
                buckets["15-30d pre"].append(p)
            else:
                buckets["30+d or no earnings"].append(p)

        result = {}
        for bucket_name, bucket_pairs in buckets.items():
            if bucket_pairs:
                returns = [p["forward_return"] for p in bucket_pairs]
                result[bucket_name] = {
                    "avg_return": round(np.mean(returns), 2),
                    "median_return": round(np.median(returns), 2),
                    "win_rate": round(sum(1 for r in returns if r > 0) / len(returns) * 100, 1),
                    "count": len(returns),
                    "std_dev": round(float(np.std(returns)), 2),
                }
            else:
                result[bucket_name] = {"count": 0}

        return result

    return {
        "status": "ok",
        "lookback_days": days,
        "forward_14d": _analyze_by_earnings_window(pairs_14d, "14d"),
        "forward_30d": _analyze_by_earnings_window(pairs_30d, "30d"),
        "data_points_14d": len(pairs_14d),
        "data_points_30d": len(pairs_30d),
        "timestamp": datetime.now().isoformat(),
    }


def run_full_backtest(days=180, forward_period=30):
    """Run all three backtest analyses and return combined results."""
    return {
        "score_vs_returns": backtest_score_vs_returns(days, forward_period),
        "layer_attribution": backtest_layer_attribution(days, forward_period),
        "earnings_timing": backtest_earnings_timing(days),
        "metadata": {
            "lookback_days": days,
            "forward_period": forward_period,
            "timestamp": datetime.now().isoformat(),
        }
    }


# ─────────────────────────────────────────────
# SELF-CALIBRATION ENGINE
# ─────────────────────────────────────────────

def calibrate_weights(days=180, forward_period=30, dry_run=False):
    """
    Auto-adjust scoring weights based on component-return correlations.

    Algorithm:
    1. Measure each component's correlation with forward returns
    2. Components with higher correlation get more weight
    3. Components with negative correlation get penalized
    4. Normalize so total still sums to 100

    Returns the proposed new weights and their backtest metrics.
    """
    attribution = backtest_layer_attribution(days, forward_period)
    if attribution.get("status") != "ok":
        return {"status": "insufficient_data", "message": "Need more backtest data to calibrate."}

    # Current weights
    from core.scanner import get_weights, set_weights, DEFAULT_LT_WEIGHTS, DEFAULT_OPT_WEIGHTS
    current = get_weights()

    results = {}

    # Calibrate LT weights
    lt_attr = attribution.get("lt_component_attribution", {})
    if lt_attr:
        lt_new = _compute_new_weights(
            current_weights=current["lt"],
            attributions=lt_attr,
            default_weights=DEFAULT_LT_WEIGHTS,
            component_prefix="lt_",
        )
        results["lt_weights"] = {
            "current": current["lt"],
            "proposed": lt_new["weights"],
            "changes": lt_new["changes"],
            "reason": lt_new["reason"],
        }

    # Calibrate options weights
    opt_attr = attribution.get("opt_component_attribution", {})
    if opt_attr:
        opt_new = _compute_new_weights(
            current_weights=current["opt"],
            attributions=opt_attr,
            default_weights=DEFAULT_OPT_WEIGHTS,
            component_prefix="opt_",
        )
        results["opt_weights"] = {
            "current": current["opt"],
            "proposed": opt_new["weights"],
            "changes": opt_new["changes"],
            "reason": opt_new["reason"],
        }

    # Apply if not dry run
    if not dry_run:
        if "lt_weights" in results:
            new_lt = results["lt_weights"]["proposed"]
            set_weights(lt_weights=new_lt)

            # Run backtest with new weights to measure improvement
            new_backtest = _quintile_analysis(days, forward_period, "lt_score")
            save_score_weights(
                "lt", new_lt,
                correlation=new_backtest.get("correlation"),
                quintile_spread=new_backtest.get("quintile_spread"),
                data_points=new_backtest.get("data_points"),
                notes=f"Auto-calibrated from {days}d backtest",
            )
            results["lt_weights"]["backtest_after"] = {
                "correlation": new_backtest.get("correlation"),
                "quintile_spread": new_backtest.get("quintile_spread"),
            }

        if "opt_weights" in results:
            new_opt = results["opt_weights"]["proposed"]
            set_weights(opt_weights=new_opt)
            save_score_weights(
                "opt", new_opt,
                data_points=attribution.get("data_points"),
                notes=f"Auto-calibrated from {days}d backtest",
            )

    results["status"] = "calibrated" if not dry_run else "dry_run"
    results["timestamp"] = datetime.now().isoformat()
    return results


def _compute_new_weights(current_weights, attributions, default_weights, component_prefix):
    """
    Compute new weights from attributions.

    Strategy:
    - Start from current weights
    - Boost components with positive correlation (up to 2x)
    - Reduce components with negative/zero correlation (down to 0.3x)
    - Normalize to sum to 100
    - Limit each adjustment to ±30% of current to avoid wild swings
    """
    raw_weights = {}
    changes = {}

    for comp_name, current_w in current_weights.items():
        attr_key = f"{component_prefix}{comp_name}"
        attr = attributions.get(attr_key, {})
        corr = attr.get("correlation", 0)

        # Compute multiplier based on correlation
        if corr > 0.1:
            mult = 1.0 + min(0.3, corr * 2)  # max +30%
        elif corr > 0.02:
            mult = 1.0 + corr * 5  # slight boost
        elif corr > -0.02:
            mult = 1.0  # no change
        elif corr > -0.1:
            mult = 1.0 + corr * 3  # slight reduction
        else:
            mult = max(0.7, 1.0 + corr * 2)  # max -30%

        new_w = current_w * mult
        raw_weights[comp_name] = new_w
        changes[comp_name] = {
            "correlation": corr,
            "multiplier": round(mult, 3),
            "old": current_w,
            "new_raw": round(new_w, 1),
        }

    # Normalize to sum to 100
    total = sum(raw_weights.values())
    if total > 0:
        normalized = {k: round(v / total * 100, 1) for k, v in raw_weights.items()}
    else:
        normalized = dict(default_weights)

    # Ensure minimum weight of 3 for any component
    for k in normalized:
        if normalized[k] < 3:
            normalized[k] = 3.0

    # Re-normalize after minimums
    total = sum(normalized.values())
    normalized = {k: round(v / total * 100, 1) for k, v in normalized.items()}

    for comp_name in changes:
        changes[comp_name]["new_final"] = normalized[comp_name]

    # Build reason string
    boosted = [k for k, v in changes.items() if v["multiplier"] > 1.05]
    reduced = [k for k, v in changes.items() if v["multiplier"] < 0.95]

    reason_parts = []
    if boosted:
        reason_parts.append(f"Boosted: {', '.join(boosted)}")
    if reduced:
        reason_parts.append(f"Reduced: {', '.join(reduced)}")
    if not boosted and not reduced:
        reason_parts.append("No significant changes — current weights are reasonable.")

    return {
        "weights": normalized,
        "changes": changes,
        "reason": " | ".join(reason_parts),
    }

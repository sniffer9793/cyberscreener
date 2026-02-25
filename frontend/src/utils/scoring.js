/**
 * QUAEST.TECH — Scoring Utilities
 * LT/Opt breakdown extraction, Reality Check computation, Tempering Grades.
 */

// ── Component names for display ──
const LT_COMPONENTS = [
  { key: 'rule_of_40', name: 'Rule of 40', icon: '📐' },
  { key: 'valuation', name: 'Valuation', icon: '⚖️' },
  { key: 'fcf_margin', name: 'FCF Margin', icon: '💰' },
  { key: 'trend', name: 'Trend', icon: '📈' },
  { key: 'earnings_quality', name: 'Earnings', icon: '📊' },
  { key: 'discount_momentum', name: 'Momentum', icon: '🔄' },
];

const OPT_COMPONENTS = [
  { key: 'earnings_catalyst', name: 'Catalyst', icon: '⚡' },
  { key: 'iv_context', name: 'IV Context', icon: '📉' },
  { key: 'directional', name: 'Directional', icon: '🎯' },
  { key: 'technical', name: 'Technical', icon: '🔧' },
  { key: 'liquidity', name: 'Liquidity', icon: '💧' },
  { key: 'asymmetry', name: 'Asymmetry', icon: '⚖️' },
];

/**
 * Extract LT breakdown from a score row.
 * Returns array of { key, name, icon, points, max, raw, pct }
 */
export function ltBreakdown(row) {
  if (!row) return [];
  let bd;
  try {
    bd = typeof row.lt_breakdown === 'string' ? JSON.parse(row.lt_breakdown) : row.lt_breakdown;
  } catch { return []; }
  if (!bd) return [];

  return LT_COMPONENTS.map(c => {
    const entry = bd[c.key] || {};
    const points = entry.points ?? 0;
    const max = entry.max ?? 1;
    const raw = entry.raw ?? (max > 0 ? points / max : 0);
    return { ...c, points, max, raw, pct: max > 0 ? (points / max) * 100 : 0 };
  });
}

/**
 * Extract Options breakdown from a score row.
 */
export function optBreakdown(row) {
  if (!row) return [];
  let bd;
  try {
    bd = typeof row.opt_breakdown === 'string' ? JSON.parse(row.opt_breakdown) : row.opt_breakdown;
  } catch { return []; }
  if (!bd) return [];

  return OPT_COMPONENTS.map(c => {
    const entry = bd[c.key] || {};
    const points = entry.points ?? 0;
    const max = entry.max ?? 1;
    const raw = entry.raw ?? (max > 0 ? points / max : 0);
    return { ...c, points, max, raw, pct: max > 0 ? (points / max) * 100 : 0 };
  });
}

/**
 * Reality Check scoring for options plays (0-100).
 * Evaluates risk/reward, volume, IV, and timing.
 */
export function computeRC(play) {
  if (!play) return 0;
  let score = 0;

  // Risk/reward ratio (max 30)
  const rr = play.risk_reward_ratio || play.rr_ratio || 0;
  if (rr >= 3) score += 30;
  else if (rr >= 2) score += 22;
  else if (rr >= 1.5) score += 15;
  else if (rr >= 1) score += 8;

  // Volume/OI (max 20)
  const vol = play.volume || 0;
  const oi = play.open_interest || 0;
  if (vol >= 500 && oi >= 1000) score += 20;
  else if (vol >= 100 && oi >= 500) score += 14;
  else if (vol >= 50 || oi >= 200) score += 8;

  // IV percentile (max 20)
  const ivp = play.iv_percentile || play.iv_pct || 0;
  const dir = (play.direction || '').toLowerCase();
  if (dir === 'bullish' || dir === 'call') {
    if (ivp < 30) score += 20;
    else if (ivp < 50) score += 14;
    else if (ivp < 70) score += 8;
  } else {
    if (ivp > 70) score += 20;
    else if (ivp > 50) score += 14;
    else if (ivp > 30) score += 8;
  }

  // Spread (max 15)
  const spread = play.bid_ask_spread_pct || 0;
  if (spread < 3) score += 15;
  else if (spread < 8) score += 10;
  else if (spread < 15) score += 5;

  // DTE timing (max 15)
  const dte = play.dte || 0;
  if (dte >= 14 && dte <= 60) score += 15;
  else if (dte >= 7 && dte <= 90) score += 10;
  else if (dte >= 3) score += 5;

  return Math.min(score, 100);
}

/**
 * Tempering Grades based on Sharpe ratio and drawdown.
 */
export function temperingGrade(sharpe, maxDrawdown) {
  if (sharpe == null) return { grade: 'UNTEMPERED', color: 'var(--color-text-tertiary)' };

  if (sharpe > 1.5 && (maxDrawdown == null || Math.abs(maxDrawdown) < 15)) {
    return { grade: 'DAMASCUS', color: 'var(--forge-amber)' };
  }
  if (sharpe > 1.0) {
    return { grade: 'STEEL', color: 'var(--denarius-silver)' };
  }
  if (sharpe > 0.5) {
    return { grade: 'BRONZE', color: 'var(--oxidized-bronze)' };
  }
  return { grade: 'IRON', color: 'var(--color-text-secondary)' };
}

/**
 * Get RC verdict label + color.
 */
export function rcVerdict(score) {
  if (score >= 70) return { label: 'PASS', color: 'var(--color-success)' };
  if (score >= 40) return { label: 'CAUTION', color: 'var(--color-warning)' };
  return { label: 'FAIL', color: 'var(--color-danger)' };
}

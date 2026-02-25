/**
 * QUAEST.TECH — The Anvil (Options/Plays Tab)
 * Play generation, weight tuner, Reality Check, play history.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { Card } from '../components/ui/Card';
import { Metric } from '../components/ui/Metric';
import { Badge } from '../components/ui/Badge';
import { ScoreBar } from '../components/ui/ScoreBar';
import { generatePlays, fetchPlayStatus, fetchPlayHistory, fetchWeights, updateWeights, fetchInversePlays } from '../api/endpoints';
import { computeRC, rcVerdict } from '../utils/scoring';
import { fmtExpiry, fmtTimeOnly } from '../utils/formatters';
import { useAuth } from '../auth/AuthContext';
import styles from './AnvilPage.module.css';

function MiniMetric({ label, value, color }) {
  return (
    <div className={styles.miniMetric}>
      <div className={styles.miniLabel}>{label}</div>
      <div className={styles.miniValue} style={color ? { color } : undefined}>{value}</div>
    </div>
  );
}

export function AnvilPage({ latest, defaultTicker, tz }) {
  const { isAdmin } = useAuth();
  const [sel, setSel] = useState(null);
  const [data, setData] = useState(null);
  const [msg, setMsg] = useState('');
  const [showW, setShowW] = useState(false);
  const [fetchedAt, setFetchedAt] = useState(null);
  const [tick, setTick] = useState(0);
  const [showHist, setShowHist] = useState(false);
  const [playHist, setPlayHist] = useState(null);
  const [histLoading, setHistLoading] = useState(false);
  const [ow, setOw] = useState({ earnings_catalyst: 25, iv_context: 20, directional: 20, technical: 15, liquidity: 10, asymmetry: 10 });

  const poller = useRef(null);
  const timer = useRef(null);
  const autoRef = useRef(null);

  const results = latest?.results || [];
  const opts = [...results].sort((a, b) => b.opt_score - a.opt_score);
  const wt = Object.values(ow).reduce((a, b) => a + b, 0);

  useEffect(() => { fetchWeights().then(w => { if (w?.active_weights?.opt) setOw(w.active_weights.opt); }); }, []);
  useEffect(() => { if (defaultTicker && defaultTicker !== sel) loadPlays(defaultTicker); }, [defaultTicker]);
  useEffect(() => { const id = setInterval(() => setTick(n => n + 1), 20000); return () => clearInterval(id); }, []);
  useEffect(() => () => cleanup(), []);

  function cleanup() {
    if (poller.current) clearInterval(poller.current);
    if (timer.current) clearTimeout(timer.current);
    if (autoRef.current) { clearInterval(autoRef.current); autoRef.current = null; }
    poller.current = timer.current = null;
  }

  async function loadHistory() {
    if (playHist) return;
    setHistLoading(true);
    const d = await fetchPlayHistory(50);
    if (d) setPlayHist(d);
    setHistLoading(false);
  }

  async function loadPlays(t, force = false) {
    cleanup();
    setSel(t);
    if (!force) setData(null);
    setMsg('Starting...');
    const d = await generatePlays(t);
    if (!d) { setData({ ticker: t, plays: [], error: 'Could not reach API' }); return; }

    const gotData = (r) => {
      setData(r);
      setFetchedAt(Date.now());
      if (!r.error && r.plays?.length) {
        autoRef.current = setInterval(() => loadPlays(t, true), 120000);
      }
    };

    if (d.status === 'cached') { gotData(d.result); return; }
    setMsg(d.message || 'Working...');

    poller.current = setInterval(async () => {
      const s = await fetchPlayStatus(t);
      if (!s) return;
      if (s.status === 'done') {
        if (poller.current) clearInterval(poller.current);
        if (timer.current) clearTimeout(timer.current);
        poller.current = timer.current = null;
        gotData(s.result || { ticker: t, plays: [], error: 'No data' });
      } else if (s.status === 'running') setMsg(s.message || 'Working...');
    }, 2000);

    timer.current = setTimeout(() => {
      cleanup();
      setData(prev => prev || { ticker: t, plays: [], error: 'Timed out' });
    }, 45000);
  }

  // ── Render detail panel ──
  let detail;

  if (!sel) {
    const stats = playHist?.stats;
    const plays = playHist?.plays || [];
    detail = (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <Card style={{ padding: 40, textAlign: 'center' }}>
          <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.5 }}>{'\u2694\uFE0F'}</div>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>The Anvil</div>
          <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', maxWidth: 480, margin: '0 auto', lineHeight: 1.7 }}>
            Select a ticker to forge options plays. Each includes scoring breakdown, Reality Check, and risk/reward analysis.
          </div>
        </Card>

        {/* Play history toggle */}
        <Card style={{ padding: 20, cursor: 'pointer' }} onClick={() => { if (!showHist) loadHistory(); setShowHist(s => !s); }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: showHist ? 14 : 0 }}>
            <h2 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>{'\uD83D\uDCC8'} Play History</h2>
            <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>{showHist ? '\u25B2 hide' : '\u25BC expand'}</span>
          </div>
          {showHist && (
            <div onClick={e => e.stopPropagation()}>
              {histLoading && <div className={styles.loading}>Loading play history...</div>}
              {!histLoading && plays.length === 0 && <div className={styles.loading}>No closed plays yet.</div>}
              {!histLoading && stats?.total_closed > 0 && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 14 }}>
                  <Metric label="Closed" value={stats.total_closed} />
                  <Metric label="Win Rate" value={stats.win_rate != null ? stats.win_rate + '%' : '\u2014'} color={stats.win_rate >= 55 ? 'var(--color-success)' : 'var(--color-warning)'} />
                  <Metric label="Avg P&L" value={stats.avg_pnl != null ? `${stats.avg_pnl > 0 ? '+' : ''}${stats.avg_pnl}%` : '\u2014'} color={stats.avg_pnl > 0 ? 'var(--color-success)' : 'var(--color-danger)'} />
                  <Metric label="Best Play" value={stats.best_play?.ticker || '\u2014'} sub={stats.best_play?.pnl_pct != null ? `${stats.best_play.pnl_pct > 0 ? '+' : ''}${stats.best_play.pnl_pct}%` : ''} />
                </div>
              )}
              {!histLoading && plays.length > 0 && (
                <div style={{ overflowX: 'auto' }}>
                  <table className={styles.histTable}>
                    <thead>
                      <tr>
                        {['Ticker', 'Strategy', 'Direction', 'Expiry', 'DTE', 'RC', 'Entry', 'P&L', 'Date'].map(h => (
                          <th key={h}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {plays.map((p, i) => {
                        const pnl = p.pnl_pct;
                        const pnlColor = pnl == null ? 'var(--color-text-tertiary)' : pnl > 0 ? 'var(--color-success)' : 'var(--color-danger)';
                        return (
                          <tr key={i} style={{ background: i % 2 === 0 ? 'var(--color-bg)' : 'transparent' }}>
                            <td style={{ fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{p.ticker}</td>
                            <td>{p.strategy || '\u2014'}</td>
                            <td>{(p.direction || '').charAt(0).toUpperCase() + (p.direction || '').slice(1)}</td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>{fmtExpiry(p.expiry)}</td>
                            <td>{p.dte || '\u2014'}</td>
                            <td style={{ fontWeight: 600, color: p.rc_score >= 70 ? 'var(--color-success)' : p.rc_score >= 50 ? 'var(--color-warning)' : 'var(--color-text-tertiary)' }}>{p.rc_score || '\u2014'}</td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>${p.entry_price || '\u2014'}</td>
                            <td style={{ fontWeight: 700, fontFamily: 'var(--font-mono)', color: pnlColor }}>{pnl != null ? `${pnl > 0 ? '+' : ''}${pnl}%` : '\u2014'}</td>
                            <td style={{ color: 'var(--color-text-tertiary)' }}>{p.outcome_date || p.generated_at?.slice(0, 10) || '\u2014'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </Card>

        {/* How scoring works */}
        <Card style={{ padding: 24 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>How Options Scoring Works</h3>
          <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', lineHeight: 1.7, marginBottom: 12 }}>
            The Options Score (0&ndash;100) has six weighted components:
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {[
              { n: 'Earnings Catalyst', w: ow.earnings_catalyst, d: 'Proximity to earnings \u2014 #1 IV driver. Sweet spot: 5\u201314 days out.' },
              { n: 'IV Context', w: ow.iv_context, d: 'IV rank vs history. Low = cheap (buy). High = expensive (sell/spread).' },
              { n: 'Directional Conviction', w: ow.directional, d: 'RSI, SMA alignment, volume. Strong = clear call/put bias.' },
              { n: 'Technical Setup', w: ow.technical, d: 'BB squeeze + RSI extremes. Breakout or mean-reversion signals.' },
              { n: 'Liquidity', w: ow.liquidity, d: 'Market cap and options volume. Better liquidity = tighter fills.' },
              { n: 'Asymmetry', w: ow.asymmetry, d: 'Short squeeze, high beta, whale flow. Outsized move potential.' },
            ].map(c => (
              <div key={c.n} className={styles.componentCard}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 700 }}>{c.n}</span>
                  <span className={styles.componentPts}>{c.w}pts</span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>{c.d}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    );
  } else if (!data) {
    detail = (
      <Card style={{ padding: 40, textAlign: 'center' }}>
        <div className="pulse" style={{ fontSize: 24, marginBottom: 12 }}>{'\u27F3'}</div>
        <div style={{ fontSize: 14, color: 'var(--color-text-secondary)', fontWeight: 500, marginBottom: 8 }}>Forging plays for {sel}</div>
        <div style={{ fontSize: 12, color: 'var(--color-text-tertiary)' }}>{msg}</div>
      </Card>
    );
  } else if (data.error && (!data.plays || !data.plays.length)) {
    detail = (
      <Card style={{ padding: 24 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700 }}>{sel}</h2>
        {data.price && <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-mono)', margin: '8px 0' }}>${data.price}</div>}
        <div className={styles.errorBanner}>{'\u26A0'} {data.error}</div>
      </Card>
    );
  } else {
    const p = data;
    const playsRC = (p.plays || []).map(pl => ({ ...pl, _rc: computeRC(pl), _verdict: rcVerdict(computeRC(pl)) }));
    playsRC.sort((a, b) => b._rc - a._rc);

    detail = (
      <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Header */}
        <Card style={{ padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8 }}>
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 700 }}>{p.ticker} Options Intelligence</h2>
              <p style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{playsRC.length} play{playsRC.length !== 1 ? 's' : ''} &middot; sorted by reality check</p>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>${p.price}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
                {fetchedAt && (
                  <span style={{ fontSize: 10, fontWeight: 600, color: (Date.now() - fetchedAt) < 30000 ? 'var(--color-success)' : (Date.now() - fetchedAt) < 90000 ? 'var(--color-warning)' : 'var(--color-danger)' }}>
                    {(Date.now() - fetchedAt) < 10000 ? '\u25CF Live' : (Date.now() - fetchedAt) < 60000 ? Math.round((Date.now() - fetchedAt) / 1000) + 's ago' : Math.round((Date.now() - fetchedAt) / 60000) + 'm ago'}
                  </span>
                )}
                <button className={styles.refreshBtn} onClick={e => { e.stopPropagation(); loadPlays(sel, true); }}>
                  {'\uD83D\uDD04'} Refresh
                </button>
              </div>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))', gap: 10, marginTop: 14 }}>
            <Metric label="RSI" value={p.rsi != null ? Math.round(p.rsi) : '\u2014'} color={p.rsi < 30 ? 'var(--color-success)' : p.rsi > 70 ? 'var(--color-danger)' : 'var(--color-warning)'} sub={p.rsi < 30 ? 'Oversold' : p.rsi > 70 ? 'Overbought' : 'Neutral'} />
            <Metric label="IV 30d" value={p.iv_30d != null ? p.iv_30d + '%' : '\u2014'} color={p.iv_30d > 50 ? 'var(--color-danger)' : 'var(--color-warning)'} />
            <Metric label="Earnings" value={p.days_to_earnings != null ? p.days_to_earnings + 'd' : '\u2014'} color={p.days_to_earnings != null && p.days_to_earnings <= 14 ? 'var(--color-success)' : 'var(--color-text-secondary)'} />
            <Metric label="Beta" value={p.beta != null ? Number(p.beta).toFixed(1) : '\u2014'} />
            <Metric label="Vol Ratio" value={p.vol_ratio != null ? p.vol_ratio + 'x' : '\u2014'} />
          </div>
        </Card>

        {/* Play cards */}
        {playsRC.length > 0 ? playsRC.map((pl, i) => {
          const dC = pl.direction?.includes('Bullish') ? 'var(--color-success)' : pl.direction?.includes('Bearish') ? 'var(--color-danger)' : 'var(--imperial-purple)';
          const rcScore = pl._rc;
          const verdict = pl._verdict;

          return (
            <Card key={i} style={{ borderLeft: `3px solid ${dC}`, padding: 0, overflow: 'hidden' }}>
              {/* Play header */}
              <div className={styles.playHeader}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 20 }}>{pl.emoji}</span>
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 700 }}>{pl.strategy}</div>
                    <Badge color={dC}>{pl.direction}</Badge>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{pl.action}</div>
                  <div style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>Exp: {fmtExpiry(pl.expiry)} ({pl.dte}d)</div>
                </div>
              </div>

              {/* RC score bar */}
              <div className={styles.rcBar} style={{ background: verdict.color + '08', borderBottom: `1px solid ${verdict.color}20` }}>
                <div className={styles.rcBadge} style={{ background: verdict.color + '15', color: verdict.color }}>{rcScore}</div>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: verdict.color }}>{verdict.label}</div>
                  <div style={{ fontSize: 10, color: 'var(--color-text-secondary)' }}>Reality Check</div>
                </div>
              </div>

              {/* Metrics grid */}
              <div className={styles.playMetrics}>
                <MiniMetric label="Entry" value={`$${pl.entry_price}`} />
                <MiniMetric label="Breakeven" value={pl.breakeven} />
                <MiniMetric label="Max Loss" value={`$${Number(pl.max_loss).toLocaleString()}`} color="var(--color-danger)" />
                <MiniMetric label="Max Gain" value={pl.max_gain} color="var(--color-success)" />
                {pl.bid != null && <MiniMetric label="Bid/Ask" value={`$${pl.bid} / $${pl.ask}`} />}
                <MiniMetric label="IV" value={`${pl.iv}%`} color={pl.iv > 60 ? 'var(--color-danger)' : 'var(--color-warning)'} />
                <MiniMetric label="Volume" value={Number(pl.volume).toLocaleString()} />
                <MiniMetric label="Open Int" value={Number(pl.open_interest).toLocaleString()} />
              </div>

              {/* Rationale */}
              <div className={styles.rationale}>
                <div className={styles.sectionLabel}>Rationale</div>
                <div style={{ fontSize: 12, color: 'var(--color-text)', lineHeight: 1.6 }}>{pl.rationale}</div>
              </div>

              {/* Risk notes */}
              <div className={styles.riskNotes}>{'\u26A0'} {pl.risk_notes}</div>
            </Card>
          );
        }) : (
          <Card style={{ padding: 24, textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>No plays — no earnings catalyst, low IV, or insufficient directional bias.</div>
          </Card>
        )}
      </div>
    );
  }

  return (
    <div className={`fade-in ${styles.layout}`}>
      {/* ── Sidebar ── */}
      <div className={styles.sidebar}>
        {/* Weight tuner toggle */}
        <button className={`${styles.tunerBtn} ${showW ? styles.tunerActive : ''}`} onClick={() => setShowW(!showW)}>
          {'\u2699'} Weight Tuner <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}>{showW ? '\u25BC' : '\u25B6'}</span>
        </button>

        {showW && (
          <Card style={{ padding: 16 }}>
            <div className={styles.sectionLabel}>Opt Score Weights</div>
            <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', marginBottom: 12 }}>Adjust factor contributions. Total &asymp; 100.</div>
            {[
              ['Earnings', ow.earnings_catalyst, v => setOw(p => ({ ...p, earnings_catalyst: v }))],
              ['IV Context', ow.iv_context, v => setOw(p => ({ ...p, iv_context: v }))],
              ['Directional', ow.directional, v => setOw(p => ({ ...p, directional: v }))],
              ['Technical', ow.technical, v => setOw(p => ({ ...p, technical: v }))],
              ['Liquidity', ow.liquidity, v => setOw(p => ({ ...p, liquidity: v }))],
              ['Asymmetry', ow.asymmetry, v => setOw(p => ({ ...p, asymmetry: v }))],
            ].map(([l, v, fn]) => (
              <div key={l} className={styles.sliderRow}>
                <span className={styles.sliderLabel}>{l}</span>
                <input type="range" min={0} max={40} step={1} value={v} onChange={e => fn(parseInt(e.target.value))} style={{ flex: 1 }} />
                <span className={styles.sliderVal}>{v}</span>
              </div>
            ))}
            <div className={styles.tunerFooter}>
              <span style={{ color: wt === 100 ? 'var(--color-success)' : wt > 100 ? 'var(--color-danger)' : 'var(--color-warning)' }}>
                Total: {wt}/100
              </span>
              <div style={{ display: 'flex', gap: 6 }}>
                <button className={styles.tunerAction} onClick={() => setOw({ earnings_catalyst: 25, iv_context: 20, directional: 20, technical: 15, liquidity: 10, asymmetry: 10 })}>Reset</button>
                <button className={styles.tunerApply} onClick={() => updateWeights({ opt: ow })}>Apply</button>
              </div>
            </div>
          </Card>
        )}

        {/* Ticker list */}
        <Card style={{ padding: 12, maxHeight: showW ? '40vh' : '65vh', overflowY: 'auto' }}>
          <div className={styles.sectionLabel} style={{ padding: '4px 8px', marginBottom: 4 }}>By Opt Score</div>
          {opts.map(r => (
            <div
              key={r.ticker}
              onClick={() => loadPlays(r.ticker)}
              className={`${styles.tickerRow} ${sel === r.ticker ? styles.tickerSelected : ''}`}
            >
              <span className={styles.tickerSymbol}>{r.ticker}</span>
              <span className={styles.tickerPrice}>${r.price}</span>
              <Badge color={r.opt_score >= 40 ? 'var(--color-success)' : r.opt_score >= 25 ? 'var(--color-warning)' : 'var(--color-text-tertiary)'}>
                {r.opt_score}
              </Badge>
            </div>
          ))}
        </Card>
      </div>

      {/* ── Detail ── */}
      <div style={{ flex: 1, minWidth: 0 }}>{detail}</div>
    </div>
  );
}

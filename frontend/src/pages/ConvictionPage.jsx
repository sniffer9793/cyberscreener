/**
 * QUAEST.TECH — Conviction Board (Long Tab)
 * Ticker list with sector filters, detail panel with score breakdowns,
 * intel layers, signals feed, score history chart, and price chart.
 */

import { useState, useCallback, useMemo } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Card } from '../components/ui/Card';
import { Metric } from '../components/ui/Metric';
import { Badge } from '../components/ui/Badge';
import { ScoreBar } from '../components/ui/ScoreBar';
import { LayerPill } from '../components/ui/LayerPill';
import { BreakdownPanel } from '../components/ui/BreakdownPanel';
import { SvgAreaChart } from '../components/charts/SvgAreaChart';
import { SvgPriceChart } from '../components/charts/SvgPriceChart';
import { fetchScoreHistory, fetchSignals } from '../api/endpoints';
import { ltBreakdown, optBreakdown } from '../utils/scoring';
import { fmtDateOnly } from '../utils/formatters';
import styles from './ConvictionPage.module.css';

const ALL_FILTERS = [
  ['all', 'All'], ['cyber', 'Cyber'], ['energy', 'Energy'], ['defense', 'Defense'],
  ['tech', 'Tech'], ['health', 'Health'], ['finance', 'Finance'],
  ['consumer', 'Consumer'], ['industrial', 'Industrial'], ['broad', 'Broad'],
];

function applyFilter(r, filter) {
  if (filter === 'all') return true;
  if (filter === 'cyber' || filter === 'energy' || filter === 'defense') return r.sector === filter;
  if (filter === 'tech') return r.sector === 'broad' && r.subsector === 'Technology';
  if (filter === 'health') return r.sector === 'broad' && r.subsector === 'Health Care';
  if (filter === 'finance') return r.sector === 'broad' && r.subsector === 'Financials';
  if (filter === 'consumer') return r.sector === 'broad' && (r.subsector === 'Consumer Disc' || r.subsector === 'Consumer Staples');
  if (filter === 'industrial') return r.sector === 'broad' && r.subsector === 'Industrials';
  if (filter === 'broad') return r.sector === 'broad';
  return true;
}

export function ConvictionPage({ latest }) {
  const { personalScores } = useAuth();
  const [sel, setSel] = useState(null);
  const [hist, setHist] = useState(null);
  const [filter, setFilter] = useState('all');
  const [signals, setSignals] = useState(null);
  const [showSig, setShowSig] = useState(false);

  const results = latest?.results || [];

  // Build personal scores lookup
  const psMap = useMemo(() => {
    if (!personalScores?.scores) return {};
    const m = {};
    personalScores.scores.forEach(s => { m[s.ticker] = s; });
    return m;
  }, [personalScores]);

  const load = useCallback(async (ticker) => {
    setSel(ticker);
    setHist(null);
    setSignals(null);
    setShowSig(false);
    const d = await fetchScoreHistory(ticker, 180);
    if (d) setHist(d);
  }, []);

  const lr = sel ? results.find(r => r.ticker === sel) : null;
  const L = hist?.history?.length ? hist.history[hist.history.length - 1] : null;
  const F = hist?.history?.length ? hist.history[0] : null;
  const cd = hist?.history?.map(h => ({
    date: fmtDateOnly(h.timestamp),
    lt_score: h.lt_score,
    opt_score: h.opt_score,
    price: h.price,
    rsi: h.rsi,
  })) || [];

  const filtered = results.filter(r => applyFilter(r, filter));
  const hasPS = Object.keys(psMap).length > 0;

  return (
    <div className={`fade-in ${styles.layout}`}>
      {/* ── Ticker List Panel ── */}
      <div className={styles.sidebar}>
        <div className={styles.filters}>
          {ALL_FILTERS.map(([s, l]) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`${styles.filterBtn} ${filter === s ? styles.filterActive : ''}`}
            >
              {l}
            </button>
          ))}
        </div>

        <Card style={{ padding: 12, maxHeight: '65vh', overflowY: 'auto' }}>
          <div className={styles.tickerCount}>{filtered.length} tickers</div>
          {filtered.map(r => {
            const sd = r.short_delta;
            const isBuyZone = r.lt_score >= 55 && r.rsi <= 45;
            const ps = psMap[r.ticker];
            const selected = sel === r.ticker;

            return (
              <div
                key={r.ticker}
                onClick={() => load(r.ticker)}
                className={`${styles.tickerRow} ${selected ? styles.tickerSelected : ''}`}
              >
                <span className={styles.tickerSymbol}>{r.ticker}</span>
                <div className={styles.tickerMeta}>
                  <span className={styles.tickerPrice}>${r.price}</span>
                  {isBuyZone && (
                    <span className={styles.buyZone}>{'🟢'} Buy Zone</span>
                  )}
                </div>
                <Badge color={r.lt_score >= 50 ? 'var(--color-success)' : r.lt_score >= 30 ? 'var(--color-warning)' : 'var(--color-text-tertiary)'}>
                  {r.lt_score}
                </Badge>
                {ps && (
                  <span
                    className={styles.personalScore}
                    title="Your Quaestor LT score"
                    style={{
                      background: ps.lt_delta > 0 ? 'var(--color-success-bg)' : ps.lt_delta < 0 ? 'var(--color-danger-bg)' : 'var(--color-bg)',
                      color: ps.lt_delta > 0 ? 'var(--color-success)' : ps.lt_delta < 0 ? 'var(--color-danger)' : 'var(--imperial-purple)',
                      borderColor: ps.lt_delta > 0 ? 'var(--oxidized-bronze-light)' : ps.lt_delta < 0 ? 'var(--forge-red-light)' : 'var(--color-border-subtle)',
                    }}
                  >
                    {Math.round(ps.user_lt_score)}
                  </span>
                )}
                <span className={styles.optScore}>{r.opt_score}</span>
                {sd != null && Math.abs(sd) >= 2 ? (
                  <span
                    className={styles.shortDelta}
                    style={{ color: sd < -3 ? 'var(--color-success)' : sd > 3 ? 'var(--color-danger)' : 'var(--color-text-tertiary)' }}
                    title={`Short interest delta: ${sd > 0 ? '+' : ''}${sd}pp (60d)`}
                  >
                    {sd < -3 ? '↓SI' : sd > 3 ? '↑SI' : '·'}
                  </span>
                ) : <span />}
              </div>
            );
          })}
        </Card>
      </div>

      {/* ── Detail Panel ── */}
      <div className={styles.detail}>
        {!sel ? (
          <Card style={{ padding: 40, textAlign: 'center' }}>
            <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.5 }}>{'📈'}</div>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>Conviction Board</div>
            <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginBottom: 10 }}>
              Long-term value positions &middot; Retirement account ideas
            </div>
            <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', maxWidth: 400, margin: '0 auto', lineHeight: 1.6 }}>
              Select a ticker to view score history, component breakdown, and layer status.
            </div>
          </Card>
        ) : !L ? (
          <Card style={{ padding: 40, textAlign: 'center' }}>
            <div className="pulse" style={{ fontSize: 14, color: 'var(--color-text-secondary)' }}>
              Loading {sel}...
            </div>
          </Card>
        ) : (
          <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Score metrics */}
            <div className={styles.metricsGrid}>
              <Metric
                label="LT Score"
                value={L.lt_score}
                color={L.lt_score >= 60 ? 'var(--color-success)' : L.lt_score >= 35 ? 'var(--color-warning)' : 'var(--color-danger)'}
                sub="System score"
              />
              {psMap[sel] && (
                <Metric
                  label={'⚔️ Your LT'}
                  value={Math.round(psMap[sel].user_lt_score)}
                  color={psMap[sel].user_lt_score >= 60 ? 'var(--color-success)' : psMap[sel].user_lt_score >= 35 ? 'var(--color-warning)' : 'var(--color-danger)'}
                  sub={`${psMap[sel].lt_delta >= 0 ? '+' : ''}${psMap[sel].lt_delta} vs system`}
                />
              )}
              <Metric
                label="Opt Score"
                value={L.opt_score}
                color={L.opt_score >= 40 ? 'var(--color-success)' : L.opt_score >= 25 ? 'var(--color-warning)' : 'var(--color-danger)'}
                sub="Options opportunity"
              />
              <Metric
                label="LT Δ"
                value={`${L.lt_score - F.lt_score >= 0 ? '+' : ''}${L.lt_score - F.lt_score}`}
                color={L.lt_score >= F.lt_score ? 'var(--color-success)' : 'var(--color-danger)'}
              />
              <Metric label="Price" value={`$${L.price}`} />
            </div>

            {/* Intel layers */}
            {lr && (
              <div className={styles.layerRow}>
                <LayerPill name="SEC" icon={'📋'} score={lr.sec_score} />
                <LayerPill name="Sent" icon={'💬'} score={lr.sentiment_score} />
                <LayerPill name="Whale" icon={'🐋'} score={lr.whale_score} />
                {lr.short_delta != null && Math.abs(lr.short_delta) >= 2 && (
                  <Badge
                    color={lr.short_delta < -3 ? 'var(--color-success)' : lr.short_delta > 3 ? 'var(--color-danger)' : 'var(--color-text-secondary)'}
                    variant="soft"
                  >
                    {lr.short_delta < -3 ? '🔻 SI covering' : '📈 SI building'}
                  </Badge>
                )}
                {lr.outage_status === 'outage' && <Badge color="var(--color-danger)" variant="soft">{'🔴'} OUTAGE</Badge>}
                {lr.outage_status === 'degraded' && <Badge color="var(--color-warning)" variant="soft">{'⚠'} DEGRADED</Badge>}
                {lr.breach_victim && <Badge color="var(--color-danger)" variant="soft">{'🚨'} BREACH</Badge>}
                {lr.demand_signal && !lr.breach_victim && <Badge color="var(--color-warning)" variant="soft">{'🌋'} DEMAND</Badge>}
              </div>
            )}

            {/* Score breakdowns */}
            {lr && (
              <div className={styles.breakdownGrid}>
                <BreakdownPanel items={ltBreakdown(lr)} title="LT Score Breakdown" accent="var(--color-success)" />
                <BreakdownPanel items={optBreakdown(lr)} title="Opt Score Breakdown" accent="var(--imperial-purple)" />
              </div>
            )}

            {/* Signals feed */}
            <Card
              style={{ padding: 20, cursor: 'pointer' }}
              onClick={async () => {
                if (!showSig && !signals) {
                  const d = await fetchSignals(sel, 40);
                  if (d) setSignals(d);
                }
                setShowSig(s => !s);
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: showSig ? 12 : 0 }}>
                <h2 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>{'📡'} Scoring Signals Feed</h2>
                <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
                  {showSig ? '▲ hide' : '▼ expand — why these scores?'}
                </span>
              </div>
              {showSig && (
                <div onClick={e => e.stopPropagation()}>
                  {!signals && <div className={styles.loading}>Loading signals...</div>}
                  {signals?.signals?.length === 0 && <div className={styles.loading}>No signals yet.</div>}
                  {signals?.signals?.map((s, i) => {
                    const col = s.impact === 'positive' ? 'var(--color-success)' : s.impact === 'negative' ? 'var(--color-danger)' : 'var(--color-text-secondary)';
                    const ic = s.impact === 'positive' ? '🟢' : s.impact === 'negative' ? '🔴' : '⚪';
                    return (
                      <div key={i} className={styles.signalRow}>
                        <span style={{ fontSize: 12, flexShrink: 0 }}>{ic}</span>
                        <span style={{ fontSize: 11, color: col, flex: 1, lineHeight: 1.4 }}>{s.signal_text}</span>
                        <span style={{ fontSize: 9, color: 'var(--color-text-tertiary)', whiteSpace: 'nowrap', marginLeft: 4 }}>
                          {s.scan_ts?.slice(0, 10) || ''}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </Card>

            {/* Score history chart */}
            <Card style={{ padding: 20 }}>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>{sel} — Score History</h2>
              <SvgAreaChart
                data={cd}
                lines={[
                  { key: 'lt_score', name: 'LT Score', color: 'var(--color-success)' },
                  { key: 'opt_score', name: 'Opt Score', color: 'var(--imperial-purple)' },
                ]}
                height={260}
              />
            </Card>

            {/* Price chart */}
            <Card style={{ padding: 20 }}>
              <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>{sel} — Price & Signals</h2>
              <SvgPriceChart ticker={sel} />
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

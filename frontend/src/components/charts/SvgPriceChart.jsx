import { useState, useEffect } from 'react';
import { ChartContainer } from './ChartContainer';
import { TimeframeSelector } from './TimeframeSelector';
import { fetchChart } from '../../api/endpoints';

/**
 * Price + SMA + RSI chart with signal markers.
 * Pixel-based rendering for readable text.
 */
export function SvgPriceChart({ ticker, days = 90 }) {
  const [data, setData] = useState(null);
  const [showSMA, setShowSMA] = useState({ s20: true, s50: true, s200: false });
  const [selDays, setSelDays] = useState(days);

  useEffect(() => {
    if (!ticker) return;
    setData(null);
    fetchChart(ticker, selDays).then(d => setData(d));
  }, [ticker, selDays]);

  if (!data) {
    return (
      <div style={{ height: 420, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-text-secondary)', fontSize: 12, background: 'var(--color-bg)', borderRadius: 12 }}>
        Loading chart...
      </div>
    );
  }

  const prices = data.prices || [];
  if (!prices.length) {
    return (
      <div style={{ height: 80, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-text-secondary)', fontSize: 12, background: 'var(--color-bg)', borderRadius: 12 }}>
        No price data
      </div>
    );
  }

  const n = prices.length;
  const sigs = data.signals || [];

  // Signal colors & icons
  const SC = {
    earnings: 'var(--color-warning)',
    insider_buy: 'var(--color-success)',
    insider_sell: 'var(--color-danger)',
    rsi_oversold: 'var(--color-success)',
    rsi_overbought: 'var(--color-danger)',
    sma_cross_bull: '#30d158',
    sma_cross_bear: 'var(--color-danger)',
  };
  const SI = { earnings: 'E', insider_buy: 'B', insider_sell: 'S', rsi_oversold: '\u25CE', rsi_overbought: '\u25CE', sma_cross_bull: '\u25B2', sma_cross_bear: '\u25BC' };

  // Map signals to indices
  const d2i = {};
  prices.forEach((p, i) => { d2i[p.date] = i; });
  const mappedSigs = sigs.map(s => {
    let idx = d2i[s.date];
    if (idx == null) {
      let best = 0, bd = Infinity;
      prices.forEach((p, i) => {
        const dd = Math.abs(new Date(p.date) - new Date(s.date));
        if (dd < bd) { bd = dd; best = i; }
      });
      idx = best;
    }
    return { ...s, idx, color: SC[s.type] || 'var(--color-info)', icon: SI[s.type] || '\u2022' };
  });

  // Price range
  const closes = prices.map(p => p.close || 0);
  const allPrices = [
    ...closes,
    ...prices.map(p => p.sma20).filter(v => v != null),
    ...prices.map(p => p.sma50).filter(v => v != null),
    ...prices.map(p => p.sma200).filter(v => v != null),
  ];
  const pMin = Math.min(...allPrices) * 0.997;
  const pMax = Math.max(...allPrices) * 1.003;
  const pR = pMax - pMin || 1;

  const fmtD = d => d ? d.slice(5) : '';

  return (
    <div style={{ width: '100%' }}>
      {/* Timeframe selector + SMA toggles */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8, flexWrap: 'wrap' }}>
        <TimeframeSelector options={[30, 60, 90, 180]} value={selDays} onChange={setSelDays} />
        <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
          {[
            { key: 's20', label: 'SMA20', color: 'var(--color-success)' },
            { key: 's50', label: 'SMA50', color: 'var(--color-warning)' },
            { key: 's200', label: 'SMA200', color: 'var(--imperial-purple-light)' },
          ].map(s => (
            <button
              key={s.key}
              onClick={() => setShowSMA(prev => ({ ...prev, [s.key]: !prev[s.key] }))}
              style={{
                padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 600,
                cursor: 'pointer', fontFamily: 'var(--font-mono)',
                background: showSMA[s.key] ? 'var(--color-bg-elevated)' : 'transparent',
                border: `1px solid ${showSMA[s.key] ? s.color : 'var(--color-border-subtle)'}`,
                color: s.color,
                opacity: showSMA[s.key] ? 1 : 0.45,
              }}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <ChartContainer height={420} marginTop={12} marginRight={20} marginBottom={50} marginLeft={56}>
        {({ width, height: h, plotArea, crosshair, setTip }) => {
          const { left, right, top } = plotArea;
          const pw = right - left;
          // Split: price panel top 70%, RSI panel bottom 30%
          const priceBottom = top + (h - top - 50) * 0.72;
          const rsiTop = priceBottom + 20;
          const rsiBottom = h - 50;
          const pricePH = priceBottom - top;
          const rsiPH = rsiBottom - rsiTop;

          const px = i => left + (i / (n - 1 || 1)) * pw;
          const py = v => priceBottom - ((v - pMin) / pR) * pricePH;
          const pyR = r => rsiBottom - (r / 100) * rsiPH;

          const makePts = getV => {
            let d = '';
            prices.forEach((p, i) => {
              const v = getV(p);
              if (v != null) d += (d ? ' ' : '') + px(i) + ',' + py(v);
            });
            return d;
          };

          // RSI line
          const rsiPts = prices.map((p, i) => p.rsi != null ? `${px(i)},${pyR(p.rsi)}` : null).filter(Boolean);
          const rsiLine = rsiPts.join(' ');
          const rsiFirst = prices.findIndex(p => p.rsi != null);
          const rsiLast = prices.length - 1 - [...prices].reverse().findIndex(p => p.rsi != null);
          const rsiFill = rsiPts.length > 1 ? `${rsiLine} ${px(rsiLast)},${rsiBottom} ${px(rsiFirst)},${rsiBottom}` : '';

          // Price line
          const priceLine = prices.map((p, i) => `${px(i)},${py(p.close || 0)}`).join(' ');
          const priceFill = `${priceLine} ${px(n - 1)},${priceBottom} ${left},${priceBottom}`;

          // Price Y-axis ticks
          const pTicks = [0, 0.25, 0.5, 0.75, 1].map(f => ({
            v: pMin + pR * f,
            y: priceBottom - f * pricePH,
          }));

          // Hovered index
          const hoveredIdx = crosshair.visible
            ? Math.max(0, Math.min(n - 1, Math.round(((crosshair.x - left) / pw) * (n - 1))))
            : -1;

          if (hoveredIdx >= 0 && hoveredIdx < n) {
            const p = prices[hoveredIdx];
            const items = [{ label: 'Close', value: '$' + (p.close || 0).toFixed(2), color: 'var(--imperial-purple)' }];
            if (p.rsi != null) items.push({ label: 'RSI', value: p.rsi.toFixed(0), color: 'var(--color-warning)' });
            if (showSMA.s20 && p.sma20) items.push({ label: 'SMA20', value: '$' + p.sma20.toFixed(0), color: 'var(--color-success)' });
            if (showSMA.s50 && p.sma50) items.push({ label: 'SMA50', value: '$' + p.sma50.toFixed(0), color: 'var(--color-warning)' });
            if (showSMA.s200 && p.sma200) items.push({ label: 'SMA200', value: '$' + p.sma200.toFixed(0), color: 'var(--imperial-purple-light)' });
            queueMicrotask(() => setTip({ x: px(hoveredIdx), y: py(p.close || 0), date: p.date, items }));
          }

          // X-axis labels
          const xCount = Math.min(6, n);
          const xLabels = [];
          for (let i = 0; i < xCount; i++) {
            const idx = Math.round((i / (xCount - 1 || 1)) * (n - 1));
            xLabels.push({ x: px(idx), label: fmtD(prices[idx]?.date) });
          }

          return (
            <g>
              {/* Price grid + Y-axis */}
              {pTicks.map((t, i) => (
                <g key={i}>
                  <line x1={left} y1={t.y} x2={right} y2={t.y}
                    stroke="var(--color-border-subtle)" strokeWidth={1} />
                  <text x={left - 6} y={t.y} fill="var(--color-text-tertiary)"
                    fontSize={10} fontFamily="var(--font-mono)" textAnchor="end" dominantBaseline="middle">
                    ${t.v.toFixed(0)}
                  </text>
                </g>
              ))}

              {/* Signal vertical lines */}
              {mappedSigs.map((s, i) => (
                <line key={`svl${i}`} x1={px(s.idx)} y1={top} x2={px(s.idx)} y2={rsiBottom}
                  stroke={s.color} strokeWidth={1} strokeDasharray="4,3" opacity={0.4} />
              ))}

              {/* Price area + line */}
              <polygon points={priceFill} fill="var(--imperial-purple)" opacity={0.06} />
              {showSMA.s200 && <polyline points={makePts(p => p.sma200)} fill="none" stroke="var(--imperial-purple-light)" strokeWidth={1.5} opacity={0.75} />}
              {showSMA.s50 && <polyline points={makePts(p => p.sma50)} fill="none" stroke="var(--color-warning)" strokeWidth={1.5} opacity={0.8} />}
              {showSMA.s20 && <polyline points={makePts(p => p.sma20)} fill="none" stroke="var(--color-success)" strokeWidth={1.5} opacity={0.8} />}
              <polyline points={priceLine} fill="none" stroke="var(--imperial-purple)" strokeWidth={2} />

              {/* Hover dot on price */}
              {hoveredIdx >= 0 && hoveredIdx < n && (
                <circle cx={px(hoveredIdx)} cy={py(prices[hoveredIdx].close || 0)}
                  r={4} fill="var(--imperial-purple)" stroke="#fff" strokeWidth={1.5} />
              )}

              {/* Signal icons */}
              {mappedSigs.filter(s => s.type !== 'rsi_oversold' && s.type !== 'rsi_overbought').map((s, i) => (
                <text key={`st${i}`} x={px(s.idx)} y={priceBottom - 6} fill={s.color}
                  fontSize={12} textAnchor="middle" fontFamily="var(--font-mono)" fontWeight="bold">
                  {s.icon}
                </text>
              ))}

              {/* Divider */}
              <line x1={left} y1={rsiTop - 10} x2={right} y2={rsiTop - 10}
                stroke="var(--color-border-subtle)" strokeWidth={1} />

              {/* RSI panel */}
              <text x={left + 2} y={rsiTop} fill="var(--color-text-secondary)" fontSize={10}
                fontFamily="var(--font-mono)" dominantBaseline="hanging">RSI</text>

              {/* RSI reference lines */}
              <line x1={left} y1={pyR(70)} x2={right} y2={pyR(70)} stroke="var(--color-danger)"
                strokeWidth={1} strokeDasharray="4,3" opacity={0.4} />
              <line x1={left} y1={pyR(30)} x2={right} y2={pyR(30)} stroke="var(--color-success)"
                strokeWidth={1} strokeDasharray="4,3" opacity={0.4} />
              <line x1={left} y1={pyR(50)} x2={right} y2={pyR(50)} stroke="var(--color-border-subtle)"
                strokeWidth={1} />

              {/* RSI labels */}
              <text x={right + 4} y={pyR(70)} fill="var(--color-danger)" fontSize={9}
                fontFamily="var(--font-mono)" dominantBaseline="middle">70</text>
              <text x={right + 4} y={pyR(30)} fill="var(--color-success)" fontSize={9}
                fontFamily="var(--font-mono)" dominantBaseline="middle">30</text>

              {/* RSI fill + line */}
              {rsiFill && <polygon points={rsiFill} fill="var(--color-warning)" opacity={0.1} />}
              {rsiLine && <polyline points={rsiLine} fill="none" stroke="var(--color-warning)" strokeWidth={1.5} />}

              {/* RSI extreme circles */}
              {mappedSigs.filter(s => s.type === 'rsi_oversold' || s.type === 'rsi_overbought').map((s, i) => (
                <circle key={`sc${i}`} cx={px(s.idx)} cy={pyR(s.type === 'rsi_oversold' ? 28 : 72)}
                  r={4} fill={s.color} opacity={0.9} />
              ))}

              {/* Hover dot on RSI */}
              {hoveredIdx >= 0 && hoveredIdx < n && prices[hoveredIdx].rsi != null && (
                <circle cx={px(hoveredIdx)} cy={pyR(prices[hoveredIdx].rsi)}
                  r={3} fill="var(--color-warning)" stroke="#fff" strokeWidth={1} />
              )}

              {/* X-axis labels */}
              {xLabels.map((xl, i) => (
                <text key={i} x={xl.x} y={rsiBottom + 16}
                  fill="var(--color-text-secondary)"
                  fontSize={10} fontFamily="var(--font-mono)"
                  textAnchor={i === 0 ? 'start' : i === xLabels.length - 1 ? 'end' : 'middle'}
                >
                  {xl.label}
                </text>
              ))}
            </g>
          );
        }}
      </ChartContainer>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 10, marginTop: 6, flexWrap: 'wrap', alignItems: 'center', fontSize: 10 }}>
        <span style={{ color: 'var(--imperial-purple)', fontWeight: 600 }}>● Price</span>
        <span style={{ color: 'var(--color-warning)', fontWeight: 600 }}>┄ RSI</span>
        <span style={{ flex: 1 }} />
        <span style={{ color: 'var(--color-warning)', fontFamily: 'var(--font-mono)', fontSize: 9 }}>E Earnings</span>
        <span style={{ color: 'var(--color-success)', fontFamily: 'var(--font-mono)', fontSize: 9 }}>B Buy</span>
        <span style={{ color: 'var(--color-danger)', fontFamily: 'var(--font-mono)', fontSize: 9 }}>S Sell</span>
        <span style={{ color: '#30d158', fontFamily: 'var(--font-mono)', fontSize: 9 }}>{'\u25B2'} Bull</span>
        <span style={{ color: 'var(--color-danger)', fontFamily: 'var(--font-mono)', fontSize: 9 }}>{'\u25BC'} Bear</span>
        <span style={{ color: 'var(--color-success)', fontFamily: 'var(--font-mono)', fontSize: 9 }}>{'\u25CE'} OS/OB</span>
      </div>
    </div>
  );
}

import { ChartContainer } from './ChartContainer';

/**
 * Vertical bar chart with hover tooltips.
 * Pixel-based rendering for readable text.
 */
export function SvgBarChart({ data, dataKey, labelKey, height = 280, colorFn }) {
  if (!data || !data.length) return null;

  const mx = Math.max(...data.map(d => Math.abs(d[dataKey] || 0)), 1);
  const hasNeg = data.some(d => (d[dataKey] || 0) < 0);

  return (
    <ChartContainer height={height} marginTop={20} marginRight={16} marginBottom={50} marginLeft={44}>
      {({ width, height: h, plotArea, setTip }) => {
        const { left, right, top, bottom } = plotArea;
        const pw = right - left;
        const ph = bottom - top;
        const baseY = hasNeg ? top + ph / 2 : bottom;
        const barZone = hasNeg ? ph / 2 : ph;
        const n = data.length;
        const groupW = pw / n;
        const barW = groupW * 0.7;
        const gap = groupW * 0.15;

        // Y-axis ticks
        const yTicks = hasNeg
          ? [{ v: mx, label: mx.toFixed(0) }, { v: 0, label: '0' }, { v: -mx, label: (-mx).toFixed(0) }]
          : [0, 0.25, 0.5, 0.75, 1].map(f => ({ v: mx * f, label: (mx * f).toFixed(0) }));

        return (
          <g>
            {/* Grid lines + Y-axis labels */}
            {yTicks.map((t, i) => {
              const y = hasNeg
                ? baseY - (t.v / mx) * barZone
                : bottom - (t.v / mx) * ph;
              return (
                <g key={i}>
                  <line x1={left} y1={y} x2={right} y2={y}
                    stroke="var(--color-border-subtle)" strokeWidth={1} />
                  <text x={left - 6} y={y} fill="var(--color-text-tertiary)"
                    fontSize={10} fontFamily="var(--font-mono)" textAnchor="end" dominantBaseline="middle">
                    {t.label}
                  </text>
                </g>
              );
            })}

            {/* Bars */}
            {data.map((d, i) => {
              const v = d[dataKey] || 0;
              const pct = Math.abs(v) / mx;
              const c = colorFn ? colorFn(d, v) : v >= 0 ? 'var(--color-success)' : 'var(--color-danger)';
              const bh = pct * barZone;
              const bx = left + i * groupW + gap;
              const by = v >= 0 ? baseY - bh : baseY;

              return (
                <g key={i}>
                  <rect
                    x={bx} y={by}
                    width={barW}
                    height={Math.max(bh, 1)}
                    fill={c} opacity={0.8} rx={3}
                    onMouseEnter={e => {
                      const r = e.currentTarget.closest('div').getBoundingClientRect();
                      setTip({
                        x: bx + barW / 2,
                        y: by - 8,
                        date: d[labelKey] || '',
                        items: [{ label: 'Value', value: typeof v === 'number' ? v.toFixed(1) : v, color: c }],
                      });
                    }}
                    onMouseLeave={() => setTip(null)}
                  />
                  {/* Value label on bar */}
                  {bh > 16 && (
                    <text
                      x={bx + barW / 2} y={v >= 0 ? by + 12 : by + bh - 4}
                      fill="#fff" fontSize={9} fontFamily="var(--font-mono)" fontWeight={600}
                      textAnchor="middle"
                    >
                      {typeof v === 'number' ? v.toFixed(0) : v}
                    </text>
                  )}
                </g>
              );
            })}

            {/* X-axis labels */}
            {data.map((d, i) => {
              const x = left + i * groupW + groupW / 2;
              return (
                <text
                  key={i} x={x} y={bottom + 12}
                  fill="var(--color-text-secondary)"
                  fontSize={n > 20 ? 8 : 10}
                  fontFamily="var(--font-mono)"
                  textAnchor="middle"
                  transform={n > 10 ? `rotate(-35, ${x}, ${bottom + 12})` : undefined}
                >
                  {d[labelKey] || ''}
                </text>
              );
            })}
          </g>
        );
      }}
    </ChartContainer>
  );
}

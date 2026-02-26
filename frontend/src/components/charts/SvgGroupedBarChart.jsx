import { ChartContainer } from './ChartContainer';

/**
 * Grouped vertical bars (multi-series).
 * Pixel-based rendering for readable text.
 */
export function SvgGroupedBarChart({ data, bars, labelKey, height = 300 }) {
  if (!data || !data.length) return null;

  const mx = Math.max(...bars.flatMap(b => data.map(d => Math.abs(d[b.key] || 0))), 1);

  return (
    <ChartContainer height={height} marginTop={20} marginRight={16} marginBottom={55} marginLeft={44}>
      {({ width, height: h, plotArea, setTip }) => {
        const { left, right, top, bottom } = plotArea;
        const pw = right - left;
        const ph = bottom - top;
        const n = data.length;
        const groupW = pw / n;
        const barW = (groupW * 0.7) / bars.length;
        const gap = groupW * 0.15;

        // Y-axis ticks
        const ticks = [0, 0.25, 0.5, 0.75, 1].map(f => ({
          v: (mx * f).toFixed(0),
          y: bottom - f * ph,
        }));

        return (
          <g>
            {/* Grid + Y-axis */}
            {ticks.map((t, i) => (
              <g key={i}>
                <line x1={left} y1={t.y} x2={right} y2={t.y}
                  stroke="var(--color-border-subtle)" strokeWidth={1} />
                <text x={left - 6} y={t.y} fill="var(--color-text-tertiary)"
                  fontSize={10} fontFamily="var(--font-mono)" textAnchor="end" dominantBaseline="middle">
                  {t.v}
                </text>
              </g>
            ))}

            {/* Bars */}
            {data.flatMap((d, i) =>
              bars.map((b, j) => {
                const v = d[b.key] || 0;
                const bh = (Math.abs(v) / mx) * ph;
                const bx = left + i * groupW + gap + j * barW;
                const by = bottom - bh;

                return (
                  <g key={`${i}-${j}`}>
                    <rect
                      x={bx} y={by}
                      width={barW * 0.9}
                      height={Math.max(bh, 1)}
                      fill={b.color} opacity={0.8} rx={2}
                      onMouseEnter={() => {
                        setTip({
                          x: bx + barW / 2,
                          y: by - 8,
                          date: d[labelKey] || '',
                          items: bars.map(bb => ({
                            label: bb.name,
                            value: (d[bb.key] || 0).toFixed(1) + '%',
                            color: bb.color,
                          })),
                        });
                      }}
                      onMouseLeave={() => setTip(null)}
                    />
                    {/* Value on top of bar */}
                    {bh > 18 && (
                      <text
                        x={bx + barW * 0.45} y={by + 12}
                        fill="#fff" fontSize={9} fontFamily="var(--font-mono)" fontWeight={600}
                        textAnchor="middle"
                      >
                        {v.toFixed(1)}
                      </text>
                    )}
                  </g>
                );
              })
            )}

            {/* X-axis labels */}
            {data.map((d, i) => {
              const x = left + i * groupW + groupW / 2;
              return (
                <text key={i} x={x} y={bottom + 16}
                  fill="var(--color-text-secondary)"
                  fontSize={11} fontFamily="var(--font-mono)"
                  textAnchor="middle"
                >
                  {d[labelKey] || ''}
                </text>
              );
            })}

            {/* Legend */}
            {bars.map((b, i) => (
              <g key={b.key} transform={`translate(${left + i * 100}, ${bottom + 36})`}>
                <circle cx={0} cy={-3} r={4} fill={b.color} opacity={0.8} />
                <text x={10} y={0} fill={b.color} fontSize={11} fontWeight={600}
                  fontFamily="var(--font-body)">
                  {b.name}
                </text>
              </g>
            ))}
          </g>
        );
      }}
    </ChartContainer>
  );
}

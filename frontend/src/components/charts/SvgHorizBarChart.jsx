import { ChartContainer } from './ChartContainer';

/**
 * Horizontal bar chart with labels and values.
 * Pixel-based rendering for readable text.
 */
export function SvgHorizBarChart({ data, dataKey, labelKey, height = 240 }) {
  if (!data || !data.length) return null;

  const mx = Math.max(...data.map(d => Math.abs(d[dataKey] || 0)), 1);

  return (
    <ChartContainer height={height} marginTop={8} marginRight={16} marginBottom={8} marginLeft={140}>
      {({ width, height: h, plotArea }) => {
        const { left, right, top, bottom } = plotArea;
        const pw = right - left;
        const rowH = (bottom - top) / data.length;

        return (
          <g>
            {/* Grid lines */}
            {[0, 0.25, 0.5, 0.75, 1].map(f => (
              <line key={f} x1={left} y1={top} x2={left} y2={bottom}
                stroke="transparent" />
            ))}
            {[0.25, 0.5, 0.75, 1].map(f => (
              <line key={f} x1={left + pw * f} y1={top} x2={left + pw * f} y2={bottom}
                stroke="var(--color-border-subtle)" strokeWidth={1} opacity={0.5} />
            ))}

            {data.map((d, i) => {
              const v = d[dataKey] || 0;
              const barW = (Math.abs(v) / mx) * pw;
              const c = v >= 0 ? 'var(--color-success)' : 'var(--color-danger)';
              const by = top + i * rowH + rowH * 0.15;
              const bh = rowH * 0.7;

              return (
                <g key={i}>
                  {/* Label */}
                  <text
                    x={left - 8}
                    y={by + bh / 2}
                    fill="var(--color-text-secondary)"
                    fontSize={11}
                    fontFamily="var(--font-body)"
                    textAnchor="end"
                    dominantBaseline="middle"
                  >
                    {d[labelKey] || ''}
                  </text>
                  {/* Bar */}
                  <rect
                    x={left}
                    y={by}
                    width={Math.max(barW, 2)}
                    height={bh}
                    fill={c}
                    opacity={0.75}
                    rx={3}
                  />
                  {/* Value */}
                  <text
                    x={left + Math.max(barW, 2) + 6}
                    y={by + bh / 2}
                    fill={c}
                    fontSize={11}
                    fontFamily="var(--font-mono)"
                    fontWeight={600}
                    dominantBaseline="middle"
                  >
                    {(v > 0 ? '+' : '') + v.toFixed(1) + '%'}
                  </text>
                </g>
              );
            })}
          </g>
        );
      }}
    </ChartContainer>
  );
}

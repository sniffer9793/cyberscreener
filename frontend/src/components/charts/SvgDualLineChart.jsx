import { ChartContainer } from './ChartContainer';

/**
 * Dual-line chart (solid + dashed) with independent Y-axes.
 * Pixel-based rendering for readable text.
 */
export function SvgDualLineChart({ data, line1, line2, height = 260, xKey = 'date' }) {
  if (!data || !data.length) return null;

  const n = data.length;
  const v1 = data.map(d => d[line1.key] || 0);
  const v2 = data.map(d => d[line2.key] || 0);
  const mn1 = Math.min(...v1), mx1 = Math.max(...v1), r1 = mx1 - mn1 || 1;
  const mn2 = Math.min(...v2), mx2 = Math.max(...v2), r2 = mx2 - mn2 || 1;

  return (
    <ChartContainer height={height} marginTop={12} marginRight={50} marginBottom={50} marginLeft={50}>
      {({ width, height: h, plotArea, crosshair, setTip }) => {
        const { left, right, top, bottom } = plotArea;
        const pw = right - left;
        const ph = bottom - top;

        const px = i => left + (i / (n - 1 || 1)) * pw;
        const py1 = v => bottom - ((v - mn1) / r1) * ph;
        const py2 = v => bottom - ((v - mn2) / r2) * ph;

        const pts1 = data.map((d, i) => `${px(i)},${py1(d[line1.key] || 0)}`).join(' ');
        const pts2 = data.map((d, i) => `${px(i)},${py2(d[line2.key] || 0)}`).join(' ');

        // Y-axis ticks for line1 (left) and line2 (right)
        const yTicks = [0, 0.25, 0.5, 0.75, 1];

        // Hovered index
        const hoveredIdx = crosshair.visible
          ? Math.round(((crosshair.x - left) / pw) * (n - 1))
          : -1;

        if (hoveredIdx >= 0 && hoveredIdx < n) {
          const d = data[hoveredIdx];
          queueMicrotask(() => setTip({
            x: px(hoveredIdx),
            y: py1(d[line1.key] || 0),
            date: d[xKey] || '',
            items: [
              { label: line1.name, value: (d[line1.key] || 0).toFixed(2), color: line1.color },
              { label: line2.name, value: (d[line2.key] || 0).toFixed(2), color: line2.color },
            ],
          }));
        }

        // X-axis labels
        const xCount = Math.min(5, n);
        const xLabels = [];
        for (let i = 0; i < xCount; i++) {
          const idx = Math.round((i / (xCount - 1 || 1)) * (n - 1));
          xLabels.push({ idx, x: px(idx), label: data[idx]?.[xKey] || '' });
        }

        return (
          <g>
            {/* Grid + Y-axis left (line1) */}
            {yTicks.map((f, i) => {
              const y = bottom - f * ph;
              const val1 = mn1 + r1 * f;
              const val2 = mn2 + r2 * f;
              return (
                <g key={i}>
                  <line x1={left} y1={y} x2={right} y2={y}
                    stroke="var(--color-border-subtle)" strokeWidth={1} />
                  <text x={left - 6} y={y} fill={line1.color}
                    fontSize={10} fontFamily="var(--font-mono)" textAnchor="end" dominantBaseline="middle">
                    {val1.toFixed(1)}
                  </text>
                  <text x={right + 6} y={y} fill={line2.color}
                    fontSize={10} fontFamily="var(--font-mono)" textAnchor="start" dominantBaseline="middle">
                    {val2.toFixed(1)}
                  </text>
                </g>
              );
            })}

            {/* Lines */}
            <polyline points={pts1} fill="none" stroke={line1.color} strokeWidth={2} />
            <polyline points={pts2} fill="none" stroke={line2.color} strokeWidth={1.5} strokeDasharray="6,4" />

            {/* Hover dots */}
            {hoveredIdx >= 0 && hoveredIdx < n && (
              <>
                <circle cx={px(hoveredIdx)} cy={py1(data[hoveredIdx][line1.key] || 0)}
                  r={4} fill={line1.color} stroke="#fff" strokeWidth={1.5} />
                <circle cx={px(hoveredIdx)} cy={py2(data[hoveredIdx][line2.key] || 0)}
                  r={4} fill={line2.color} stroke="#fff" strokeWidth={1.5} />
              </>
            )}

            {/* X-axis labels */}
            {xLabels.map((xl, i) => (
              <text key={i} x={xl.x} y={bottom + 16}
                fill="var(--color-text-secondary)"
                fontSize={10} fontFamily="var(--font-mono)"
                textAnchor={i === 0 ? 'start' : i === xLabels.length - 1 ? 'end' : 'middle'}
              >
                {xl.label}
              </text>
            ))}

            {/* Legend */}
            <g transform={`translate(${left}, ${bottom + 36})`}>
              <circle cx={0} cy={-3} r={4} fill={line1.color} />
              <text x={10} y={0} fill={line1.color} fontSize={11} fontWeight={600}>
                {line1.name}
              </text>
            </g>
            <g transform={`translate(${left + 120}, ${bottom + 36})`}>
              <line x1={-4} y1={-3} x2={12} y2={-3} stroke={line2.color} strokeWidth={2} strokeDasharray="4,3" />
              <text x={18} y={0} fill={line2.color} fontSize={11} fontWeight={600}>
                {line2.name}
              </text>
            </g>
          </g>
        );
      }}
    </ChartContainer>
  );
}

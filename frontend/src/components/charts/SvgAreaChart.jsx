import { ChartContainer } from './ChartContainer';

/**
 * Multi-line area chart with fill, crosshair, and structured tooltips.
 * Pixel-based rendering for readable text.
 */
export function SvgAreaChart({ data, lines, height = 320, xKey = 'date' }) {
  if (!data || !data.length) return null;

  const n = data.length;
  const allV = lines.flatMap(l => data.map(d => d[l.key] || 0));
  const mn = Math.min(...allV);
  const mx = Math.max(...allV);
  const rng = mx - mn || 1;

  return (
    <ChartContainer height={height} marginTop={12} marginRight={20} marginBottom={50} marginLeft={44}>
      {({ width, height: h, plotArea, crosshair, setTip }) => {
        const { left, right, top, bottom } = plotArea;
        const pw = right - left;
        const ph = bottom - top;

        const px = i => left + (i / (n - 1 || 1)) * pw;
        const py = v => bottom - ((v - mn) / rng) * ph;

        // Y-axis ticks (5 evenly spaced)
        const yTicks = [0, 0.25, 0.5, 0.75, 1].map(f => ({
          v: mn + rng * f,
          y: bottom - f * ph,
        }));

        // X-axis labels — show ~6 dates evenly spaced
        const xCount = Math.min(6, n);
        const xLabels = [];
        for (let i = 0; i < xCount; i++) {
          const idx = Math.round((i / (xCount - 1 || 1)) * (n - 1));
          xLabels.push({ idx, x: px(idx), label: data[idx]?.[xKey] || '' });
        }

        // Determine hovered data index from crosshair
        const hoveredIdx = crosshair.visible
          ? Math.round(((crosshair.x - left) / pw) * (n - 1))
          : -1;

        // Update tooltip on crosshair move
        if (hoveredIdx >= 0 && hoveredIdx < n) {
          const d = data[hoveredIdx];
          const tipX = px(hoveredIdx);
          const tipY = py(d[lines[0]?.key] || 0);
          const tipData = {
            x: tipX,
            y: tipY,
            date: d[xKey] || '',
            items: lines.map(l => ({
              label: l.name,
              value: typeof d[l.key] === 'number' ? d[l.key].toFixed(1) : (d[l.key] || '0'),
              color: l.color,
            })),
          };
          // Use queueMicrotask to avoid setState during render
          queueMicrotask(() => setTip(tipData));
        }

        return (
          <g>
            {/* Grid + Y-axis */}
            {yTicks.map((t, i) => (
              <g key={i}>
                <line x1={left} y1={t.y} x2={right} y2={t.y}
                  stroke="var(--color-border-subtle)" strokeWidth={1} />
                <text x={left - 6} y={t.y} fill="var(--color-text-tertiary)"
                  fontSize={10} fontFamily="var(--font-mono)" textAnchor="end" dominantBaseline="middle">
                  {t.v.toFixed(0)}
                </text>
              </g>
            ))}

            {/* Area fills + lines */}
            {lines.map(l => {
              const pts = data.map((d, i) => `${px(i)},${py(d[l.key] || 0)}`).join(' ');
              return (
                <g key={l.key}>
                  <polygon points={`${pts} ${px(n - 1)},${bottom} ${left},${bottom}`} fill={l.color} opacity={0.08} />
                  <polyline points={pts} fill="none" stroke={l.color} strokeWidth={2} />
                </g>
              );
            })}

            {/* Hover dot */}
            {hoveredIdx >= 0 && hoveredIdx < n && lines.map(l => (
              <circle key={l.key}
                cx={px(hoveredIdx)} cy={py(data[hoveredIdx][l.key] || 0)}
                r={4} fill={l.color} stroke="#fff" strokeWidth={1.5}
              />
            ))}

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
            {lines.map((l, i) => (
              <g key={l.key} transform={`translate(${left + i * 100}, ${bottom + 36})`}>
                <circle cx={0} cy={-3} r={4} fill={l.color} />
                <text x={10} y={0} fill={l.color} fontSize={11} fontWeight={600}
                  fontFamily="var(--font-body)">
                  {l.name}
                </text>
              </g>
            ))}
          </g>
        );
      }}
    </ChartContainer>
  );
}

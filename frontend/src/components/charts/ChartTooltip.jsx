/**
 * Shared tooltip component for SVG charts.
 * Supports both legacy format (tip.text) and new structured format (tip.items).
 *
 * Legacy:  { x, y, text: 'string' }
 * New:     { x, y, date: 'Feb 24', items: [{ label, value, color }] }
 */
export function ChartTooltip({ tip, containerWidth }) {
  if (!tip) return null;

  // Edge detection: flip to left side when near right boundary
  const flipThreshold = containerWidth ? containerWidth - 200 : 600;
  const isFlipped = tip.x > flipThreshold;
  const left = isFlipped ? tip.x - 180 : tip.x + 12;

  // Legacy format — single text string
  if (tip.text) {
    return (
      <div
        className="svgtip"
        style={{ left, top: Math.max(0, tip.y - 36) }}
      >
        {tip.text}
      </div>
    );
  }

  // Structured format
  if (!tip.items || !tip.items.length) return null;

  return (
    <div
      className="svgtip"
      style={{
        left,
        top: Math.max(0, tip.y - 20),
        whiteSpace: 'normal',
        minWidth: 140,
        padding: '8px 12px',
      }}
    >
      {tip.date && (
        <div style={{
          fontSize: 10,
          color: 'var(--denarius-silver)',
          marginBottom: 4,
          fontFamily: 'var(--font-mono)',
        }}>
          {tip.date}
        </div>
      )}
      {tip.items.map((item, i) => (
        <div key={i} style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 11,
          lineHeight: '18px',
          fontFamily: 'var(--font-mono)',
        }}>
          {item.color && (
            <span style={{
              display: 'inline-block',
              width: 7,
              height: 7,
              borderRadius: '50%',
              background: item.color,
              flexShrink: 0,
            }} />
          )}
          <span style={{ color: 'var(--denarius-silver-light)' }}>{item.label}:</span>
          <span style={{ color: '#fff', fontWeight: 600, marginLeft: 'auto' }}>{item.value}</span>
        </div>
      ))}
    </div>
  );
}

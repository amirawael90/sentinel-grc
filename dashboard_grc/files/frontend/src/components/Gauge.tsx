import { gaugeColor } from '../grcUtils'

interface GaugeProps {
  value: number
  label: string
  hint?: string
  active?: boolean
  onClick?: () => void
}

const RADIUS = 60
const HALF_CIRCLE = Math.PI * RADIUS

export function Gauge({ value, label, hint, active, onClick }: GaugeProps) {
  const clamped = Math.max(0, Math.min(100, value))
  const color = gaugeColor(clamped)
  const arc = `M ${80 - RADIUS} 80 A ${RADIUS} ${RADIUS} 0 0 1 ${80 + RADIUS} 80`

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      style={{
        background: 'var(--bg-elevated)',
        border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
        boxShadow: active ? '0 0 0 2px var(--accent-soft)' : 'none',
        borderRadius: 14,
        padding: '14px 12px 12px',
        cursor: onClick ? 'pointer' : 'default',
        color: 'var(--text)',
        textAlign: 'center',
      }}
    >
      <svg viewBox="0 0 160 96" width="100%" style={{ maxWidth: 190 }} role="img" aria-label={`${label} ${clamped}%`}>
        <path d={arc} fill="none" stroke="var(--bg-panel)" strokeWidth={14} strokeLinecap="round" />
        {clamped > 0 ? (
          <path
            d={arc}
            fill="none"
            stroke={color}
            strokeWidth={14}
            strokeLinecap="round"
            strokeDasharray={`${(clamped / 100) * HALF_CIRCLE} ${HALF_CIRCLE}`}
          />
        ) : null}
        <text x="80" y="76" textAnchor="middle" fontSize="26" fontWeight="700" fill="currentColor">
          {clamped}%
        </text>
      </svg>
      <div style={{ fontWeight: 600, fontSize: 14 }}>{label}</div>
      {hint ? <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>{hint}</div> : null}
    </button>
  )
}

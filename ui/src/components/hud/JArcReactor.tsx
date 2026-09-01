import { useEffect, useId, useState } from 'react'

export interface JArcReactorProps {
  /** Power / Readiness level 0-100 */
  level?: number
  /** Color accent */
  color?: 'cyan' | 'amber' | 'green' | 'red' | 'ice'
  /** Label */
  label?: string
  /** Animate outer ring */
  animated?: boolean
  size?: number
}

/**
 * Adapted from donor 03 JArcReactor.tsx and donor 07 ArcReactor.tsx.
 * Power level is server-derived; renders multi-tiered rings, 3 petal paths, and glow.
 */
export function JArcReactor({
  level = 100,
  color = 'cyan',
  label,
  animated = true,
  size = 120,
}: JArcReactorProps) {
  const [reduced, setReduced] = useState(false)
  const id = useId().replaceAll(':', '')
  const filterId = `arc-glow-${id}`

  useEffect(() => {
    const query = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!query) return
    const update = () => setReduced(query.matches)
    update()
    query.addEventListener?.('change', update)
    return () => query.removeEventListener?.('change', update)
  }, [])

  const pct = Math.max(0, Math.min(100, level)) / 100
  const cx = 50
  const cy = 50
  const r1 = 44 // outer ring
  const r2 = 34 // level arc
  const r3 = 22 // inner rotating
  const r4 = 10 // core

  const circum2 = 2 * Math.PI * r2
  const dash2 = circum2 * pct
  const gap2 = circum2 * (1 - pct)

  // Triangle petals at 120° intervals (from Donor 03)
  const petals = [0, 120, 240].map((deg) => {
    const rad = (deg * Math.PI) / 180
    const tip = {
      x: cx + r3 * Math.cos(rad - Math.PI / 2),
      y: cy + r3 * Math.sin(rad - Math.PI / 2),
    }
    const b1 = {
      x: cx + r4 * Math.cos(rad - Math.PI / 2 + 0.6),
      y: cy + r4 * Math.sin(rad - Math.PI / 2 + 0.6),
    }
    const b2 = {
      x: cx + r4 * Math.cos(rad - Math.PI / 2 - 0.6),
      y: cy + r4 * Math.sin(rad - Math.PI / 2 - 0.6),
    }
    return `M ${tip.x.toFixed(2)} ${tip.y.toFixed(2)} L ${b1.x.toFixed(2)} ${b1.y.toFixed(2)} L ${b2.x.toFixed(2)} ${b2.y.toFixed(2)} Z`
  })

  const strokeColor =
    color === 'red'
      ? 'var(--signal-crimson, #EA2F42)'
      : color === 'amber'
      ? 'var(--spark, #F29361)'
      : color === 'ice' || color === 'green'
      ? 'var(--ice-blue, #96D8EE)'
      : 'var(--jarvis-cyan, #55D9FF)'

  return (
    <div
      className="reactor-wrap"
      aria-label={label ? `${label}: ${Math.round(pct * 100)} percent` : `Core state ${Math.round(pct * 100)} percent`}
      role="img"
      style={{ width: size }}
    >
      <svg
        className={animated && !reduced ? 'reactor animated' : 'reactor'}
        viewBox="0 0 100 100"
        aria-hidden="true"
      >
        <defs>
          <filter id={filterId} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="1.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Outer static track */}
        <circle className="reactor-track" cx={cx} cy={cy} r={r1} />

        {/* Rotating outer dash track */}
        <circle
          className="reactor-dash-ring"
          cx={cx}
          cy={cy}
          r={r1}
          stroke={strokeColor}
          strokeWidth={1}
          strokeDasharray="4 8"
          opacity={0.5}
        />

        {/* Level arc (middle ring) */}
        <circle
          className="reactor-value"
          cx={cx}
          cy={cy}
          r={r2}
          stroke={strokeColor}
          strokeWidth={2.5}
          strokeDasharray={`${dash2} ${gap2}`}
          strokeDashoffset={circum2 * 0.25}
          strokeLinecap="round"
          filter={`url(#${filterId})`}
        />

        {/* Inner rotating ring */}
        <circle
          className="reactor-inner"
          cx={cx}
          cy={cy}
          r={r3}
          stroke={strokeColor}
          strokeWidth={0.8}
          strokeDasharray="2 5"
          opacity={0.45}
        />

        {/* Petal triangles */}
        {petals.map((d, i) => (
          <path
            key={i}
            d={d}
            fill={strokeColor}
            opacity={0.65 * pct}
            filter={`url(#${filterId})`}
          />
        ))}

        {/* Core circle */}
        <circle
          className="reactor-core"
          cx={cx}
          cy={cy}
          r={r4}
          fill={strokeColor}
          opacity={0.25 + 0.5 * pct}
          filter={`url(#${filterId})`}
        />
        <circle
          cx={cx}
          cy={cy}
          r={r4}
          fill="none"
          stroke={strokeColor}
          strokeWidth={1}
          opacity={0.8}
        />

        {/* Percentage text */}
        <text
          x={cx}
          y={cy + 3.5}
          textAnchor="middle"
          fill={strokeColor}
        >
          {Math.round(pct * 100)}
        </text>
      </svg>
      {label && <span className="reactor-label">{label}</span>}
    </div>
  )
}

import { useEffect, useState } from 'react'

/** Adapted from donor 03 JArcReactor (MIT); level is always server-derived. */
export function JArcReactor({ level = 100, color = 'cyan', label, animated = true }: { level?: number; color?: 'cyan' | 'amber' | 'green' | 'red'; label?: string; animated?: boolean }) {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const query = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!query) return
    const update = () => setReduced(query.matches)
    update(); query.addEventListener?.('change', update)
    return () => query.removeEventListener?.('change', update)
  }, [])
  const pct = Math.max(0, Math.min(100, level))
  const stroke = color === 'green' ? 'var(--jarvis-green)' : color === 'amber' ? 'var(--jarvis-amber)' : color === 'red' ? 'var(--jarvis-red)' : 'var(--jarvis-cyan)'
  const radius = 41
  const circumference = 2 * Math.PI * radius
  return <div className="reactor-wrap" aria-label={label ? `${label}: ${Math.round(pct)} percent` : `Core state ${Math.round(pct)} percent`} role="img">
    <svg className={animated && !reduced ? 'reactor animated' : 'reactor'} viewBox="0 0 100 100" aria-hidden="true">
      <circle className="reactor-track" cx="50" cy="50" r="41" />
      <circle className="reactor-value" cx="50" cy="50" r={radius} stroke={stroke} strokeDasharray={`${circumference}`} strokeDashoffset={circumference * (1 - pct / 100)} />
      <circle className="reactor-inner" cx="50" cy="50" r="27" stroke={stroke} /><circle className="reactor-core" cx="50" cy="50" r="12" fill={stroke} />
      <text x="50" y="54" textAnchor="middle">{Math.round(pct)}</text>
    </svg>
    {label && <span className="reactor-label">{label}</span>}
  </div>
}

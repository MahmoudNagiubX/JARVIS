import type { ReactNode } from 'react'

/**
 * Lightweight SVG adaptation of donor 08_tactical_hud gauge, compass, and
 * radar composition. Fictional targeting semantics and continuous WebGL are
 * deliberately excluded; labels are supplied by real JARVIS projections.
 */
export function ContextCompass({ label = 'LOCAL CONTEXT', value = 'UNOBSERVED' }: { label?: string; value?: ReactNode }) {
  return <div className="context-compass" aria-label={`${label}: ${value}`}><div className="compass-line"><span>N</span><i /><span>E</span><i /><span>S</span><i /><span>W</span></div><strong>{value}</strong><small>{label}</small></div>
}

export function TacticalRadar({ points = 0, label = 'DEVICE RADAR' }: { points?: number; label?: string }) {
  const dots = Array.from({ length: Math.min(Math.max(points, 0), 8) }, (_, index) => ({ cx: 18 + ((index * 29) % 64), cy: 18 + ((index * 17) % 64) }))
  return <div className="tactical-radar" data-testid="tactical-radar" aria-label={`${label}: ${points} reported points`}><svg viewBox="0 0 100 100" role="img"><circle className="radar-ring" cx="50" cy="50" r="40" /><circle className="radar-ring" cx="50" cy="50" r="27" /><circle className="radar-ring" cx="50" cy="50" r="13" /><path className="radar-cross" d="M10 50h80M50 10v80" />{dots.map((point, index) => <circle className="radar-point" key={index} cx={point.cx} cy={point.cy} r="2" />)}</svg><span>{label}</span></div>
}

export function SystemGauge({ label, value, detail }: { label: string; value: number; detail?: string }) {
  const bounded = Math.min(Math.max(value, 0), 100)
  return <div className="system-gauge"><div className="gauge-head"><span>{label}</span><strong>{bounded}%</strong></div><div className="gauge-track"><i style={{ width: `${bounded}%` }} /></div>{detail && <small>{detail}</small>}</div>
}

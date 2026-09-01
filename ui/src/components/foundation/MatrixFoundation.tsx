import type { ReactNode } from 'react'
import type { JsonRecord } from '../../lib/format'
import { dateValue, stringValue, tone } from '../../lib/format'

/**
 * Adapted from donor 01_foundation_matrix MatrixShell, MatrixExtras, and
 * DataVizComponents. Presentation only: JARVIS projection data stays the
 * source of truth and donor mock data/routes are intentionally excluded.
 */
export function MatrixFoundation({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div data-testid="matrix-foundation" className={`matrix-foundation ${className}`.trim()}>{children}</div>
}

export function MatrixSignal({ label, value, status = 'ready' }: { label: string; value: ReactNode; status?: unknown }) {
  return <div className="matrix-signal"><span className="matrix-signal-label">{label}</span><strong className={tone(status)}>{value}</strong><span className="matrix-signal-line" /></div>
}

export function MatrixTrend({ label, values, suffix = '' }: { label: string; values: number[]; suffix?: string }) {
  const safe = values.length ? values.slice(-12) : [0]
  const max = Math.max(...safe, 1)
  const min = Math.min(...safe, 0)
  const range = Math.max(max - min, 1)
  const points = safe.map((value, index) => `${(index / Math.max(safe.length - 1, 1)) * 100},${28 - ((value - min) / range) * 22}`).join(' ')
  return <div className="matrix-trend" aria-label={`${label} trend`}><div className="matrix-trend-head"><span>{label}</span><strong>{safe[safe.length - 1]}{suffix}</strong></div><svg viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true"><polyline points={points} fill="none" vectorEffect="non-scaling-stroke" /></svg></div>
}

export function MatrixEventStrip({ events }: { events: JsonRecord[] }) {
  const recent = events.slice(-8).reverse()
  return <div className="matrix-event-strip" aria-label="Recent activity">{recent.length ? recent.map((event, index) => <div className="matrix-event" key={stringValue(event.event_id, `${event.timestamp}-${index}`)}><span className={`matrix-event-dot ${tone(event.severity)}`} /><time>{dateValue(event.timestamp)}</time><strong>{stringValue(event.category || event.type, 'runtime')}</strong><span>{stringValue(event.state || event.message, 'recorded')}</span></div>) : <span className="matrix-empty">Awaiting authoritative activity</span>}</div>
}

export function MatrixCornerMark() {
  return <span className="matrix-corner-mark" aria-hidden="true"><i /><i /><i /><i /></span>
}

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { JsonRecord } from '../../lib/format'
import { dateValue, stringValue, tone } from '../../lib/format'

/**
 * Adapted from donor 03_jarvis_ui_components JHudBar, JHudFrameCard, JOrb,
 * JActivityFeed, JKPITicker, and JCommandPalette. The adapters keep their
 * visual language while receiving only canonical JARVIS data.
 */
export function HudBar({ label = 'JARVIS / LOCAL OPERATIONS', status = 'READY', children }: { label?: string; status?: string; children?: ReactNode }) {
  return <div data-testid="hud-bar" className="hud-bar"><span className="hud-bar-label">{label}</span><span className="hud-bar-dots" aria-hidden="true"><i /><i /><i /><i /><i /><i /></span><span className="hud-bar-rule" /><span className="hud-bar-status"><i />{status}</span>{children}</div>
}

export function HudFrameCard({ title, eyebrow, children, accent = 'cyan', className = '' }: { title?: string; eyebrow?: string; children: ReactNode; accent?: 'cyan' | 'crimson' | 'ice'; className?: string }) {
  return <section className={`hud-frame-card hud-frame-${accent} ${className}`.trim()}><span className="hud-frame-corner tl" /><span className="hud-frame-corner br" />{(eyebrow || title) && <header className="hud-frame-heading">{eyebrow && <span className="eyebrow">{eyebrow}</span>}{title && <h2>{title}</h2>}</header>}<div className="hud-frame-body">{children}</div></section>
}

export function HudOrb({ state = 'ready', label = 'JARVIS', listening = false, size = 'compact' }: { state?: string; label?: string; listening?: boolean; size?: 'compact' | 'hero' }) {
  const isActive = ['ready', 'active', 'processing', 'listening', 'speaking'].includes(state.toLowerCase())
  return <div className={`hud-orb hud-orb-${size} ${tone(state)}`} aria-label={`${label} ${state}`}><div className="hud-orb-ring outer" /><div className="hud-orb-ring mid" /><div className="hud-orb-ring inner" /><div className="hud-orb-core"><strong>{label}</strong><span>{state.replaceAll('_', ' ')}</span></div><span className={`hud-orb-listen ${listening ? 'on' : ''} ${isActive ? 'active' : ''}`} /></div>
}

export function HudActivityFeed({ events, limit = 8 }: { events: JsonRecord[]; limit?: number }) {
  const items = events.slice(-limit).reverse()
  return <div className="hud-activity-feed" aria-label="Live activity feed">{items.length ? items.map((event, index) => <div className="hud-activity-row" key={stringValue(event.event_id, `${event.timestamp}-${index}`)}><span className={`hud-activity-icon ${tone(event.severity)}`}>●</span><time>{dateValue(event.timestamp)}</time><span className="hud-activity-copy">{stringValue(event.message || event.category || event.type, 'Runtime event')}</span><span className="hud-activity-state">{stringValue(event.state, 'recorded')}</span></div>) : <div className="hud-activity-empty">No live activity reported</div>}</div>
}

export function HudKpiTicker({ items }: { items: Array<{ label: string; value: ReactNode; status?: unknown }> }) {
  return <div className="hud-kpi-ticker">{items.map((item) => <div className="hud-kpi" key={item.label}><span>{item.label}</span><strong className={tone(item.status ?? item.value)}>{item.value}</strong></div>)}</div>
}

export function HudDataBadge({ label, value, detail }: { label: string; value: ReactNode; detail?: string }) {
  return <div className="hud-data-badge"><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>
}

export interface HudPaletteItem { kind: string; label: string; path: string; description?: string }

/** Adapted from donor 03 JCommandPalette; navigation only, never execution. */
export function HudCommandPalette({ items, close, onSelect }: { items: HudPaletteItem[]; close: () => void; onSelect: (item: HudPaletteItem) => void }) {
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  useEffect(() => { inputRef.current?.focus() }, [])
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return normalized ? items.filter((item) => `${item.kind} ${item.label} ${item.description || ''}`.toLowerCase().includes(normalized)) : items
  }, [items, query])
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && close()}><section className="command-palette donor-command-palette" data-testid="hud-command-palette" role="dialog" aria-modal="true" aria-label="Command palette"><div className="palette-top"><span className="eyebrow">JARVIS COMMAND PALETTE</span><kbd>ESC</kbd></div><input ref={inputRef} className="palette-input" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === 'Escape' && close()} placeholder="Find a local route or capability…" aria-label="Search command palette" /> <div className="palette-results">{filtered.length ? filtered.map((item) => <button className="palette-row" key={`${item.kind}-${item.label}`} onClick={() => onSelect(item)}><span className="palette-kind">{item.kind}</span><strong>{item.label}</strong><span className="palette-arrow">↗</span></button>) : <div className="empty-state compact"><strong>No local matches</strong><p>Search finds loaded records and routes; it never executes a tool.</p></div>}</div><div className="palette-footer"><span>ESC CLOSE</span><span>LOCAL NAVIGATION ONLY</span></div></section></div>
}

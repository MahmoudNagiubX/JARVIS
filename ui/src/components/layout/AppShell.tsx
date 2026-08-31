import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { NAV_GROUPS, labelForPath, routeForLabel } from '../../app/routes'
import { useJarvis } from '../../app/context'
import { dateValue, list, record, statusText, stringValue, tone } from '../../lib/format'
import { Button, StatusBadge } from '../common/Primitives'

function streamLabel(streamState: string): string {
  return streamState === 'live' ? 'LIVE' : streamState === 'reconnecting' ? 'RECONNECTING' : streamState === 'unavailable' ? 'SNAPSHOT' : 'LOCAL'
}

function ContextRail() {
  const { projection } = useJarvis()
  const presence = record(projection?.presence)
  const system = record(projection?.system)
  const operations = record(projection?.operations)
  const deviceCount = list(projection?.devices).length
  const approvals = list(projection?.approvals).filter((item) => stringValue(item.status, 'pending') === 'pending').length
  return <aside className="context-rail" aria-label="Current context">
    <div className="rail-heading"><span className="eyebrow">LIVE CONTEXT</span><span className="rail-pip" /></div>
    <div className="rail-section"><span className="rail-label">Active application</span><strong>{stringValue(presence.active_application || presence.active_app, 'Not observed')}</strong></div>
    <div className="rail-section"><span className="rail-label">Focused window</span><strong>{stringValue(presence.focused_window, 'Not observed')}</strong></div>
    <div className="rail-section"><span className="rail-label">Runtime</span><strong className={tone(system.runtime_state)}>{statusText(system.runtime_state || 'created')}</strong><span className="small muted">{system.offline ? 'Local / internet unavailable' : 'Local services online'}</span></div>
    <div className="rail-stats"><div><strong>{deviceCount}</strong><span>devices</span></div><div><strong>{approvals}</strong><span>approvals</span></div></div>
    <div className="rail-section"><span className="rail-label">Mode</span><strong>{stringValue(operations.mode && record(operations.mode).mode, 'Normal')}</strong><span className="small muted">{dateValue(projection?.generated_at)}</span></div>
    <div className="rail-footer">Raw screenshots and audio are not durably stored.</div>
  </aside>
}

function CommandPalette({ close }: { close: () => void }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const { projection, screenData } = useJarvis()
  const entities = useMemo(() => [
    ...NAV_GROUPS.flatMap((group) => group.items.map((item) => ({ kind: 'Screen', label: item.label, path: item.path }))),
    ...list(projection?.missions).slice(0, 10).map((item) => ({ kind: 'Mission', label: stringValue(item.title || item.request, 'Mission'), path: '/missions' })),
    ...screenData.conversations.slice(0, 10).map((item) => ({ kind: 'Conversation', label: stringValue(item.title, 'Conversation'), path: '/chat' })),
    ...screenData.memories.slice(0, 10).map((item) => ({ kind: 'Memory', label: stringValue(item.content, 'Memory'), path: '/memory' })),
  ], [projection?.missions, screenData.conversations, screenData.memories])
  const results = entities.filter((item) => item.label.toLowerCase().includes(query.toLowerCase())).slice(0, 12)
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && close()}>
    <section className="command-palette" role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="palette-top"><span className="eyebrow">JARVIS COMMAND</span><kbd>ESC</kbd></div>
      <input autoFocus className="palette-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Navigate or find local context…" aria-label="Search command palette" />
      <div className="palette-results">{results.length ? results.map((item) => <button className="palette-row" key={`${item.kind}-${item.label}`} onClick={() => { close(); navigate(item.path) }}><span className="palette-kind">{item.kind}</span><strong>{item.label}</strong><span className="palette-arrow">↗</span></button>) : <div className="empty-state compact"><strong>No local matches</strong><p>Search finds screens and loaded records; it never executes a tool.</p></div>}</div>
    </section>
  </div>
}

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { projection, error, streamState } = useJarvis()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const system = record(projection?.system)
  const state = stringValue(system.runtime_state || projection?.state, 'connecting')

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setPaletteOpen(true) }
      if (event.key === 'Escape') { setPaletteOpen(false); setDrawerOpen(false) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return <div className="app-shell">
    <a className="skip-link" href="#workspace">Skip to workspace</a>
    <header className="topbar">
      <button className="mobile-menu button quiet" onClick={() => setDrawerOpen((value) => !value)} aria-label="Open navigation">☰</button>
      <button className="brand" onClick={() => navigate('/')} aria-label="JARVIS home"><span className="brand-mark" aria-hidden="true"><i /><i /><i /></span><span><strong>J.A.R.V.I.S.</strong><small>LOCAL OPERATIONS CONSOLE</small></span></button>
      <div className="topbar-meta"><StatusBadge value={state} /><span className="connection-label"><i className={`connection-dot ${streamState}`} />{streamLabel(streamState)}</span><span className="network-label">{system.offline ? 'LOCAL' : 'LOCAL + WEB'}</span><button className="palette-trigger" onClick={() => setPaletteOpen(true)}><span>Command palette</span><kbd>Ctrl K</kbd></button></div>
    </header>
    <div className="shell-body">
      <aside className={`sidebar ${drawerOpen ? 'open' : ''}`} aria-label="Primary navigation">
        <div className="sidebar-scroll">{NAV_GROUPS.map((group) => <div className="nav-group" key={group.label}><span className="nav-label">{group.label}</span>{group.items.map((item) => <NavLink key={item.path} to={item.path} end={item.path === '/'} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} onClick={() => setDrawerOpen(false)}><span className="nav-glyph">{item.glyph}</span><span>{item.label}</span>{item.path === '/approvals' && list(projection?.approvals).filter((approval) => stringValue(approval.status, 'pending') === 'pending').length > 0 && <b className="nav-count">{list(projection?.approvals).filter((approval) => stringValue(approval.status, 'pending') === 'pending').length}</b>}</NavLink>)}</div>)}</div>
        <div className="sidebar-footer"><span className="status-line"><i className="connection-dot live" />Owner session active</span><span className="muted small">{labelForPath(location.pathname)}</span></div>
      </aside>
      <main id="workspace" className="workspace">{error && <div className="global-error" role="alert"><strong>Runtime notice</strong><span>{error}</span></div>}{children}</main>
      <ContextRail />
    </div>
    {paletteOpen && <CommandPalette close={() => setPaletteOpen(false)} />}
  </div>
}

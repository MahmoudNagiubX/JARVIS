import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { NAV_GROUPS, PRIMARY_NAV_GROUPS, labelForPath } from '../../app/routes'
import { useJarvis } from '../../app/context'
import { dateValue, list, record, statusText, stringValue, tone } from '../../lib/format'
import { StatusBadge } from '../common/Primitives'
import { MatrixFoundation } from '../foundation/MatrixFoundation'
import { HudBar, HudCommandPalette, type HudPaletteItem } from '../hud/DonorFusion'
import { deriveVisualState } from '../../features/core/deriveVisualState'

function streamLabel(streamState: string): string {
  return streamState === 'live' ? 'LIVE' : streamState === 'reconnecting' ? 'RECONNECTING' : streamState === 'unavailable' ? 'SNAPSHOT' : 'LOCAL'
}

function ContextRail({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const { projection } = useJarvis()
  const presence = record(projection?.presence)
  const system = record(projection?.system)
  const operations = record(projection?.operations)
  const deviceCount = list(projection?.devices).length
  const approvals = list(projection?.approvals).filter((item) => stringValue(item.status, 'pending') === 'pending').length

  return (
    <aside
      className={`context-rail context-dock ${collapsed ? 'is-collapsed' : ''}`}
      aria-label="Current context"
    >
      <div className="rail-heading">
        <span className="eyebrow">LIVE CONTEXT</span>
        <button
          className="shell-toggle"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-label="Toggle context dock"
        >
          {collapsed ? '‹' : '›'}
        </button>
        <span className="rail-pip" />
      </div>
      {!collapsed && (
        <>
          <div className="rail-section">
            <span className="rail-label">Active App</span>
            <strong>{stringValue(presence.active_application || presence.active_app, 'Waiting for context')}</strong>
          </div>
          <div className="rail-section">
            <span className="rail-label">Focus Window</span>
            <strong>{stringValue(presence.focused_window, 'Waiting for context')}</strong>
          </div>
          <div className="rail-section">
            <span className="rail-label">Runtime</span>
            <strong className={tone(system.runtime_state)}>{statusText(system.runtime_state || 'ready')}</strong>
            <span className="small muted">{system.offline ? 'Local only' : 'Online'}</span>
          </div>
          <div className="rail-stats">
            <div>
              <strong>{deviceCount}</strong>
              <span>devices</span>
            </div>
            <div>
              <strong>{approvals}</strong>
              <span>approvals</span>
            </div>
          </div>
          <div className="rail-section">
            <span className="rail-label">Mode</span>
            <strong>{stringValue(operations.mode && record(operations.mode).mode, 'Normal')}</strong>
            <span className="small muted">{dateValue(projection?.generated_at)}</span>
          </div>
          <div className="rail-footer">Local telemetry stream active.</div>
        </>
      )}
    </aside>
  )
}

function paletteItems(projection: Record<string, unknown> | null, conversations: JsonRecord[], memories: JsonRecord[]): HudPaletteItem[] {
  return [
    ...NAV_GROUPS.flatMap((group) => group.items.map((item) => ({ kind: group.label, label: item.label, path: item.path }))),
    ...list(projection?.missions).slice(0, 10).map((item) => ({ kind: 'Mission', label: stringValue(item.title || item.request, 'Mission'), path: '/missions' })),
    ...conversations.slice(0, 10).map((item) => ({ kind: 'Conversation', label: stringValue(item.title, 'Conversation'), path: '/chat' })),
    ...memories.slice(0, 10).map((item) => ({ kind: 'Memory', label: stringValue(item.content, 'Memory'), path: '/memory' })),
  ]
}

type JsonRecord = Record<string, unknown>

function humanizeRuntimeError(message: string): string {
  if (message.includes('principal_not_found')) return 'JARVIS could not restore the owner session.'
  if (message.toLowerCase().includes('provider unavailable')) return 'The local brain is unavailable right now.'
  if (message.toLowerCase().includes('offline')) return 'Web research is unavailable while offline; local capabilities remain available.'
  return message
}

function CommandPalette({ close }: { close: () => void }) {
  const navigate = useNavigate()
  const { projection, screenData } = useJarvis()
  return (
    <HudCommandPalette
      items={paletteItems(projection, screenData.conversations, screenData.memories)}
      close={close}
      onSelect={(item) => {
        close()
        navigate(item.path)
      }}
    />
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { projection, error, streamState } = useJarvis()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [navCollapsed, setNavCollapsed] = useState(false)
  const [contextDockCollapsed, setContextDockCollapsed] = useState(false)
  const system = record(projection?.system)
  const state = stringValue(system.runtime_state || projection?.state, 'connecting')
  const visualState = deriveVisualState(projection)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen(true)
      }
      if (event.key === 'Escape') {
        setPaletteOpen(false)
        setDrawerOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <MatrixFoundation>
      <div
        className={`app-shell ${navCollapsed ? 'nav-rail-collapsed' : ''} ${contextDockCollapsed ? 'context-dock-collapsed' : ''}`}
        data-visual-state={visualState}
      >
        <a className="skip-link" href="#workspace">
          Skip to workspace
        </a>

        {/* Minimal Command Strip Topbar */}
        <header className="topbar">
          <button
            className="mobile-menu button quiet"
            onClick={() => setDrawerOpen((value) => !value)}
            aria-label="Open navigation"
          >
            ☰
          </button>

          <button className="brand" onClick={() => navigate('/')} aria-label="JARVIS home">
            <span className="brand-mark" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            <span>
              <strong>J.A.R.V.I.S.</strong>
              <small>COMMAND CONSOLE</small>
            </span>
          </button>

          <div className="topbar-meta">
            <StatusBadge value={state} />
            <span className="connection-label">
              <i className={`connection-dot ${streamState}`} />
              {streamLabel(streamState)}
            </span>
            <span className="network-label">{system.offline ? 'LOCAL' : 'LOCAL + WEB'}</span>
            <button
              className="shell-toggle"
              onClick={() => setNavCollapsed((value) => !value)}
              aria-expanded={!navCollapsed}
              aria-label="Toggle navigation rail"
            >
              ☰
            </button>
            <button
              className="shell-toggle"
              onClick={() => setContextDockCollapsed((value) => !value)}
              aria-expanded={!contextDockCollapsed}
              aria-label="Toggle context dock"
            >
              ◫
            </button>
            <button className="palette-trigger" onClick={() => setPaletteOpen(true)}>
              <span>Command palette</span>
              <kbd>Ctrl K</kbd>
            </button>
          </div>
        </header>

        <div className="topbar-trace">
          <HudBar label="JARVIS // COMMAND CENTER" status={statusText(state)}>
            <span className="topbar-trace-detail">{system.offline ? 'LOCAL MODE' : 'LOCAL + WEB'}</span>
          </HudBar>
        </div>

        <div className="shell-body">
          {/* Collapsible Cinematic Nav Rail */}
          <aside className={`sidebar ${drawerOpen ? 'open' : ''}`} aria-label="Primary navigation">
            <div className="sidebar-scroll">
              {PRIMARY_NAV_GROUPS.map((group) => (
                <div className="nav-group" key={group.label}>
                  <span className="nav-label">{group.label}</span>
                  {group.items.map((item) => (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      end={item.path === '/'}
                      title={item.label}
                      aria-label={item.label === 'Converse' ? 'Converse (Chat)' : item.label}
                      className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                      onClick={() => setDrawerOpen(false)}
                    >
                      <span className="nav-glyph">{item.glyph}</span>
                      <span className="nav-item-label">{item.label}</span>
                      {item.path === '/approvals' &&
                        list(projection?.approvals).filter(
                          (approval) => stringValue(approval.status, 'pending') === 'pending'
                        ).length > 0 && (
                          <b className="nav-count">
                            {
                              list(projection?.approvals).filter(
                                (approval) => stringValue(approval.status, 'pending') === 'pending'
                              ).length
                            }
                          </b>
                        )}
                    </NavLink>
                  ))}
                </div>
              ))}
            </div>
            <div className="sidebar-footer">
              <span className="sr-only">Workspace</span>
              <span className="status-line">
                <i className="connection-dot live" />
                Session Active
              </span>
              <span className="muted small">{labelForPath(location.pathname)}</span>
            </div>
          </aside>

          {/* Expansive Workspace Area */}
          <main id="workspace" className="workspace">
            {error && (
              <div className="global-error" role="alert">
                <span className="notice-mark">!</span>
                <div>
                  <strong>Local session needs attention</strong>
                  <span>{humanizeRuntimeError(error)}</span>
                </div>
              </div>
            )}
            <div className="workspace-route-view">{children}</div>
          </main>

          {/* Collapsible Context Dock */}
          <ContextRail
            collapsed={contextDockCollapsed}
            onToggle={() => setContextDockCollapsed((value) => !value)}
          />
        </div>

        {paletteOpen && <CommandPalette close={() => setPaletteOpen(false)} />}
      </div>
    </MatrixFoundation>
  )
}

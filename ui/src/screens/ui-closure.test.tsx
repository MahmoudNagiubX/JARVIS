import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from '../app/App'
import type { ApiClient, JarvisSession } from '../lib/api'
import type { ExperienceState } from '../lib/events'

const session: JarvisSession = {
  owner_id: 'owner-1', identity_id: 'identity-1', device_id: 'device-1', csrf_token: 'csrf-1',
}

const baseProjection: ExperienceState = {
  system: { runtime_state: 'ready', offline: true, model_available: true, model_alias: 'local-qwen' },
  approvals: [], missions: [], notifications: [], devices: [], goals: [], skills: [], automations: [], timeline: [], presence: {}, home: {}, voice: {},
}

function apiFor(projection: ExperienceState, post: ReturnType<typeof vi.fn>, getOverrides: Record<string, unknown> = {}): ApiClient {
  const get = vi.fn(async (path: string) => {
    if (getOverrides[path] !== undefined) return getOverrides[path]
    if (path === '/experience/state') return projection
    if (path === '/conversations') return { conversations: [] }
    return {}
  })
  return { session: null, setSession: vi.fn(), get, post, patch: vi.fn(), delete: vi.fn() } as unknown as ApiClient
}

describe('Phase 14 final closure screens', () => {
  beforeEach(() => { window.location.hash = '#/' })
  afterEach(() => { vi.useRealTimers() })

  it('refreshes the desktop session before expiry through the canonical API', async () => {
    vi.useFakeTimers()
    const now = Date.now()
    const initial = { ...session, expires_at: new Date(now + 120_000).toISOString() }
    const refreshed = { ...initial, csrf_token: 'csrf-rotated', expires_at: new Date(now + 240_000).toISOString() }
    const post = vi.fn(async (path: string) => path === '/auth/session/refresh' ? refreshed : {})
    const api = apiFor(baseProjection, post)
    render(<App api={api} initialSession={initial} />)

    await vi.advanceTimersByTimeAsync(60_001)
    expect(post).toHaveBeenCalledWith('/auth/session/refresh', {})
  })

  it('shows a recoverable message when desktop session renewal fails', async () => {
    vi.useFakeTimers()
    const now = Date.now()
    const initial = { ...session, expires_at: new Date(now + 120_000).toISOString() }
    const post = vi.fn(async () => { throw new Error('session unavailable') })
    const api = apiFor(baseProjection, post)
    render(<App api={api} initialSession={initial} />)

    await vi.advanceTimersByTimeAsync(60_001)
    await Promise.resolve()
    await Promise.resolve()
    expect(screen.getByText('Session expired. Reopen JARVIS.')).toBeInTheDocument()
  })

  it('sends the backend run correlation once from the approval center', async () => {
    window.location.hash = '#/approvals'
    const projection = { ...baseProjection, approvals: [{ approval_id: 'approval-1', action: 'tool.computer.action', status: 'pending', run_id: 'run-1' }] }
    const post = vi.fn(async () => ({}))
    const api = apiFor(projection, post)
    render(<App api={api} initialSession={session} />)

    const approve = await screen.findByRole('button', { name: 'Approve' })
    fireEvent.click(approve)
    fireEvent.click(approve)
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1))
    expect(post).toHaveBeenCalledWith('/approvals/approval-1', { run_id: 'run-1', approved: true })
  })

  it('starts chat through the async transport and exposes cancel while the run is active', async () => {
    window.location.hash = '#/chat'
    let cancelled = false
    const projection = { ...baseProjection }
    const post = vi.fn(async (path: string) => {
      if (path === '/messages/start') return { run_id: 'run-1', conversation_id: 'conversation-1', session_id: 'session-1', state: 'queued' }
      if (path === '/runs/run-1/cancel') { cancelled = true; return { run_id: 'run-1', state: 'cancelled' } }
      return {}
    })
    const api = apiFor(projection, post, {
      '/conversations/conversation-1/messages': { messages: [] },
      '/runs/run-1': { run_id: 'run-1', conversation_id: 'conversation-1', state: 'queued' },
    })
    render(<App api={api} initialSession={session} />)
    const composer = await screen.findByRole('textbox', { name: 'Message JARVIS' })
    fireEvent.change(composer, { target: { value: 'cancel this run' } })
    fireEvent.click(screen.getByRole('button', { name: /Send message/ }))
    expect(await screen.findByRole('button', { name: 'Cancel run' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel run' }))
    await waitFor(() => expect(cancelled).toBe(true))
    expect(post).toHaveBeenCalledWith('/runs/run-1/cancel')
  })

  it('renders activity from the run-scoped activity endpoint', async () => {
    window.location.hash = '#/chat'
    const projection = { ...baseProjection }
    const post = vi.fn(async () => ({}))
    const api = apiFor(projection, post, {
      '/conversations': { conversations: [{ id: 'conversation-1', title: 'Activity', updated_at: '2026-08-31T12:00:00Z' }] },
      '/conversations/conversation-1/messages': { messages: [{ id: 'message-1', run_id: 'run-1', role: 'assistant', content: 'Done', created_at: '2026-08-31T12:00:00Z' }] },
      '/runs/run-1/activity': { run_id: 'run-1', tools: [{ tool_call_id: 'tool-1', name: 'computer.observe', status: 'completed' }] },
    })
    render(<App api={api} initialSession={session} />)
    fireEvent.click(await screen.findByRole('button', { name: /Activity/ }))
    expect(await screen.findByText('computer.observe')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/runs/run-1/activity')
  })

  it('renders non-empty research evidence from the canonical response envelope', async () => {
    window.location.hash = '#/research'
    const post = vi.fn(async () => ({}))
    const api = apiFor(baseProjection, post, {
      '/research/runs': { runs: [{ run_id: 'research-1', query: 'local proof', status: 'completed', created_at: '2026-08-31T12:00:00Z' }] },
      '/research/runs/research-1/evidence': { evidence: [{ evidence_id: 'evidence-1', source: 'local source', excerpt: 'grounded result' }] },
    })
    render(<App api={api} initialSession={session} />)
    fireEvent.click(await screen.findByRole('button', { name: 'View evidence' }))
    expect(await screen.findByText('grounded result')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/research/runs/research-1/evidence')
  })

  it('filters notification views and does not present settings self-links as controls', async () => {
    const notificationProjection = {
      ...baseProjection,
      notifications: [
        { notification_id: 'normal', title: 'Runtime Notice', message: 'runtime notice', source: 'runtime', severity: 'info', dismissed: false },
        { notification_id: 'important', title: 'Important', message: 'important', source: 'runtime', severity: 'critical', dismissed: false },
        { notification_id: 'system', title: 'System', message: 'system', source: 'system', severity: 'info', dismissed: true },
      ],
    }
    const post = vi.fn(async () => ({}))
    const api = apiFor(notificationProjection, post)
    window.location.hash = '#/notifications'
    const view = render(<App api={api} initialSession={session} />)
    expect(await screen.findByText('Runtime Notice')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Important' }))
    expect(screen.getAllByText('Important').length).toBeGreaterThan(0)
    expect(screen.queryByText('Runtime Notice')).not.toBeInTheDocument()

    view.unmount()
    window.location.hash = '#/settings'
    const settingsApi = apiFor(baseProjection, vi.fn(async () => ({})), { '/health': {}, '/personalization/profile': {} })
    render(<App api={settingsApi} initialSession={session} />)
    await screen.findByText('Settings & health')
    expect(screen.queryByRole('link', { name: /^General/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /^Advanced diagnostics/ })).not.toBeInTheDocument()
  })

  it('renders only backend-confirmed MCP health and namespaced capabilities', async () => {
    window.location.hash = '#/settings'
    const api = apiFor(baseProjection, vi.fn(async () => ({})), {
      '/health': {
        state: 'ready', database: 'connected',
        mcp: [{
          server_id: 'workspace', display_name: 'Workspace', state: 'ready', tool_count: 3,
          capabilities: [{ name: 'mcp.workspace.read_file' }],
        }],
        venom: {}, local_model: {},
      },
      '/personalization/profile': {},
    })
    render(<App api={api} initialSession={session} />)
    expect(await screen.findByText('MCP capabilities')).toBeInTheDocument()
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/health'))
    expect(screen.getAllByText('Workspace').length).toBeGreaterThan(1)
    expect(screen.getByText(/discovered tools/)).toBeInTheDocument()
    expect(screen.getByText('mcp.workspace.read_file')).toBeInTheDocument()
    expect(screen.queryByText('No MCP servers configured')).not.toBeInTheDocument()
  })

  it('renders the wallpaper-led donor-fusion command center surfaces', async () => {
    const api = apiFor({
      ...baseProjection,
      presence: { active_application: 'JARVIS', focused_window: 'Command Center' },
      missions: [{ mission_id: 'mission-1', title: 'Review owner queue', status: 'active', current_step: 'Inspecting' }],
      timeline: [{ event_id: 'event-1', category: 'runtime', state: 'ready', timestamp: '2026-09-01T08:00:00Z' }],
    }, vi.fn(async () => ({})))
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByTestId('wallpaper-hero')).toBeInTheDocument()
    expect(screen.getByTestId('hero-art')).toBeInTheDocument()
    expect(screen.getByTestId('matrix-foundation')).toBeInTheDocument()
    expect(screen.getByTestId('hud-bar')).toBeInTheDocument()
    expect(screen.getByText('Review owner queue')).toBeInTheDocument()
    expect(screen.getByText('LOCAL CAPABILITY SPINE')).toBeInTheDocument()
  })

  it('exposes accessible controls for collapsing both shell docks', async () => {
    const api = apiFor(baseProjection, vi.fn(async () => ({})))
    render(<App api={api} initialSession={session} />)

    await screen.findByTestId('wallpaper-hero')
    const navToggle = screen.getByRole('button', { name: 'Toggle navigation rail' })
    const contextToggles = screen.getAllByRole('button', { name: 'Toggle context dock' })
    expect(navToggle).toHaveAttribute('aria-expanded', 'true')
    expect(contextToggles[0]).toHaveAttribute('aria-expanded', 'true')

    fireEvent.click(navToggle)
    fireEvent.click(contextToggles[0])
    expect(navToggle).toHaveAttribute('aria-expanded', 'false')
    expect(contextToggles[0]).toHaveAttribute('aria-expanded', 'false')
  })

  it('keeps recoverable runtime messaging calm and human-readable', async () => {
    const api = apiFor(baseProjection, vi.fn(async () => ({})))
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByText('Internet is unavailable. Local capabilities remain available.')).toBeInTheDocument()
    expect(screen.queryByText('principal_not_found')).not.toBeInTheDocument()
    expect(screen.queryByText('RUNTIME NOTICE')).not.toBeInTheDocument()
  })

  it('exposes the rich donor-derived chat surfaces over the existing transport', async () => {
    window.location.hash = '#/chat'
    const api = apiFor(baseProjection, vi.fn(async () => ({})), { '/conversations': { conversations: [] } })
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByTestId('conversation-rail')).toBeInTheDocument()
    expect(screen.getByText('BACKGROUND INBOX')).toBeInTheDocument()
  })

  it('exposes mission pipeline and plan presentation from real mission data', async () => {
    window.location.hash = '#/missions'
    const projection = { ...baseProjection, missions: [{ mission_id: 'mission-1', title: 'Prepare briefing', status: 'active', current_step: 'Collecting context' }] }
    const api = apiFor(projection, vi.fn(async () => ({})))
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByTestId('mission-pipeline')).toBeInTheDocument()
    expect(screen.getByText('EXECUTION PLAN')).toBeInTheDocument()
  })

  it('keeps every canonical mission status visible in the pipeline', async () => {
    window.location.hash = '#/missions'
    const projection = {
      ...baseProjection,
      missions: [
        { mission_id: 'mission-running', title: 'Running mission', status: 'running', current_step: 'Executing' },
        { mission_id: 'mission-failed', title: 'Failed mission', status: 'failed', current_step: 'Stopped' },
      ],
    }
    const api = apiFor(projection, vi.fn(async () => ({})))
    render(<App api={api} initialSession={session} />)

    const pipeline = await screen.findByTestId('mission-pipeline')
    expect(pipeline).toHaveTextContent('Running mission')
    expect(pipeline).toHaveTextContent('Failed mission')
  })

  it('uses tactical presentation for the device surface without inventing health', async () => {
    window.location.hash = '#/devices'
    const projection = { ...baseProjection, devices: [{ device_id: 'nightfury', name: 'NIGHTFURY', status: 'available', capabilities: ['presence'] }] }
    const api = apiFor(projection, vi.fn(async () => ({})))
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByTestId('tactical-radar')).toBeInTheDocument()
    expect(screen.getByText('NIGHTFURY')).toBeInTheDocument()
  })

  it('binds the tactical topology point count to real registered devices', async () => {
    window.location.hash = '#/devices'
    const projection = {
      ...baseProjection,
      devices: [
        { device_id: 'nightfury', name: 'NIGHTFURY', status: 'available', capabilities: ['presence'] },
        { device_id: 'atlas', name: 'ATLAS', status: 'available', capabilities: ['computer.observe'] },
      ],
    }
    const api = apiFor(projection, vi.fn(async () => ({})))
    render(<App api={api} initialSession={session} />)

    const radar = await screen.findByTestId('tactical-radar')
    expect(radar).toHaveAttribute('data-reported-points', '2')
    expect(within(radar).getAllByTestId('radar-point')).toHaveLength(2)
  })
})

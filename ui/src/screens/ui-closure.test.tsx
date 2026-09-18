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

  it('renders memory lattice with confidence meter and allows opening edit modal', async () => {
    window.location.hash = '#/memory'
    const memories = [
      {
        memory_id: 'mem-1',
        content: 'Prefers dark mode and local-first execution.',
        category: 'preference',
        confidence: 90,
        source: 'conversation',
        sensitivity: 'low',
        validity: 'valid',
      },
    ]
    const api = apiFor(baseProjection, vi.fn(async () => ({})), { '/memory?limit=50': { memories } })
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByTestId('memory-screen')).toBeInTheDocument()
    expect(await screen.findByText('Prefers dark mode and local-first execution.')).toBeInTheDocument()
    expect(screen.getByTestId('confidence-meter')).toHaveTextContent('90%')

    // Open edit modal
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    expect(screen.getByRole('heading', { name: 'Edit memory' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Content' })).toHaveValue('Prefers dark mode and local-first execution.')

    // Close edit modal
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('heading', { name: 'Edit memory' })).not.toBeInTheDocument()
  })

  it('renders situational context with focus vector compass and bounded facts', async () => {
    window.location.hash = '#/context'
    const projection = {
      ...baseProjection,
      presence: {
        focused_window: 'Visual Studio Code',
        active_application: 'Code.exe',
        active_device_id: 'DESKTOP-JARVIS',
      },
    }
    const api = apiFor(projection, vi.fn(async () => ({})), {
      '/context': {
        world_state: { 'network.online': true, 'audio.muted': false },
      },
    })
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByTestId('context-screen')).toBeInTheDocument()
    expect(screen.getAllByText('Visual Studio Code').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Code.exe').length).toBeGreaterThan(0)
    expect(screen.getByText('Desktop and presence')).toBeInTheDocument()
  })

  it('renders engineering worker delegator surface with code output and artifact metrics', async () => {
    window.location.hash = '#/engineering'
    const projection = {
      ...baseProjection,
      worker_delegations: [
        {
          session_id: 'worker-1',
          worker_id: 'worker-codex',
          provider: 'Codex CLI',
          status: 'running',
          last_action: 'Running tests',
          artifact_count: 3,
          verification_status: 'unverified',
          output: 'PASS src/screens/ui-closure.test.tsx\nAll tests completed.',
        },
      ],
    }
    const api = apiFor(projection, vi.fn(async () => ({})))
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByTestId('engineering-screen')).toBeInTheDocument()
    expect(screen.getByText('Codex CLI')).toBeInTheDocument()
    expect(screen.getAllByText('3').length).toBeGreaterThan(0)
    expect(screen.getByText('unverified')).toBeInTheDocument()
    expect(screen.getByText(/PASS src\/screens\/ui-closure.test.tsx/)).toBeInTheDocument()
    expect(screen.getByText('canonical-worker-output.txt')).toBeInTheDocument()
  })

  it('renders browser safe capability surface with deferred state and approval link', async () => {
    window.location.hash = '#/browser'
    const api = apiFor(baseProjection, vi.fn(async () => ({})))
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByTestId('browser-screen')).toBeInTheDocument()
    expect(screen.getByText('No live browser job')).toBeInTheDocument()
    expect(screen.getByText(/The product UI will display real browser capability results/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review approvals' })).toHaveAttribute('href', '#/approvals')
  })

  it('allows starting a research run and cancelling an active run', async () => {
    window.location.hash = '#/research'
    const post = vi.fn(async () => ({}))
    const api = apiFor(baseProjection, post, {
      '/research/runs': {
        runs: [
          { run_id: 'run-active', query: 'Quantum algorithms', status: 'running', created_at: '2026-08-31T12:00:00Z' },
        ],
      },
    })
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByTestId('research-screen')).toBeInTheDocument()
    expect(await screen.findByText('Quantum algorithms')).toBeInTheDocument()

    // Start a new research run
    const input = screen.getByRole('textbox', { name: 'Research request' })
    fireEvent.change(input, { target: { value: 'Neural architectures' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start research' }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/research/runs', { query: 'Neural architectures' }))

    // Cancel active run
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/research/runs/run-active/cancel', {}))
  })

  it('allows toggling skill enablement through canonical skills API', async () => {
    window.location.hash = '#/skills'
    const post = vi.fn(async () => ({}))
    const projection = {
      ...baseProjection,
      skills: [
        {
          skill_id: 'skill-python',
          name: 'Python Execution',
          description: 'Executes sandboxed Python scripts.',
          enabled: true,
          status: 'enabled',
          source: 'Product registry',
          version: '1.2.0',
          risk_level: 'medium',
          capabilities: [{ name: 'python.run' }],
        },
      ],
    }
    const api = apiFor(projection, post)
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByTestId('skills-screen')).toBeInTheDocument()
    expect(screen.getAllByText('Python Execution').length).toBeGreaterThan(0)
    expect(screen.getByText('Executes sandboxed Python scripts.')).toBeInTheDocument()

    const disableBtn = screen.getByRole('button', { name: 'Disable' })
    fireEvent.click(disableBtn)
    await waitFor(() => expect(post).toHaveBeenCalledWith('/skills/skill-python/disable', {}))
  })

  it('allows dismissing unread notifications through canonical notifications API', async () => {
    window.location.hash = '#/notifications'
    const post = vi.fn(async () => ({}))
    const projection = {
      ...baseProjection,
      notifications: [
        {
          notification_id: 'notif-1',
          title: 'High Temperature Alert',
          message: 'Reactor temperature is elevated.',
          severity: 'critical',
          dismissed: false,
          created_at: '2026-08-31T12:00:00Z',
        },
      ],
    }
    const api = apiFor(projection, post)
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByTestId('notifications-screen')).toBeInTheDocument()
    expect(screen.getByText('High Temperature Alert')).toBeInTheDocument()

    const dismissBtn = screen.getByRole('button', { name: 'Dismiss' })
    fireEvent.click(dismissBtn)
    await waitFor(() => expect(post).toHaveBeenCalledWith('/notifications/notif-1/dismiss', {}))
  })

  it('allows denying a pending approval with canonical run correlation', async () => {
    window.location.hash = '#/approvals'
    const post = vi.fn(async () => ({}))
    const projection = {
      ...baseProjection,
      approvals: [
        {
          approval_id: 'approval-2',
          action: 'file.delete',
          reason: 'Deleting temporary logs',
          risk: 'high',
          status: 'pending',
          run_id: 'run-99',
        },
      ],
    }
    const api = apiFor(projection, post)
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByTestId('approvals-screen')).toBeInTheDocument()
    expect(screen.getByText('file.delete')).toBeInTheDocument()

    const denyBtn = screen.getByRole('button', { name: 'Deny' })
    fireEvent.click(denyBtn)
    await waitFor(() => expect(post).toHaveBeenCalledWith('/approvals/approval-2', { run_id: 'run-99', approved: false }))
  })

  it('renders activity timeline events with audit projection and timestamps', async () => {
    window.location.hash = '#/activity'
    const projection = {
      ...baseProjection,
      timeline: [
        {
          event_id: 'event-1',
          event_type: 'session.restored',
          category: 'session',
          severity: 'info',
          timestamp: '2026-08-31T12:00:00Z',
        },
      ],
    }
    const api = apiFor(projection, vi.fn(async () => ({})))
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByTestId('activity-screen')).toBeInTheDocument()
    expect(screen.getByText('1 RECORDED EVENTS')).toBeInTheDocument()
    expect(screen.getByText('session restored')).toBeInTheDocument()
  })

  it('renders settings diagnostic health, MCP capabilities, and privacy boundary', async () => {
    window.location.hash = '#/settings'
    const projection = {
      ...baseProjection,
      system: {
        runtime_state: 'ready',
        offline: false,
        model_available: true,
        model_alias: 'local-qwen',
        model_provider: 'Local Ollama',
      },
      voice: {
        state: 'listening',
        microphone: 'Default Mic',
        speaker: 'Default Output',
      },
    }
    const api = apiFor(projection, vi.fn(async () => ({})), {
      '/health': {
        state: 'ready',
        database: 'Connected SQLite',
        local_model: { available: true, provider: 'Local Ollama' },
        mcp: [
          {
            server_id: 'filesystem-server',
            display_name: 'Local Filesystem MCP',
            tool_count: 5,
            state: 'ready',
            capabilities: [{ name: 'fs.read' }, { name: 'fs.write' }],
          },
        ],
      },
      '/personalization/profile': { owner_name: 'Tony Stark' },
    })
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByTestId('settings-screen')).toBeInTheDocument()
    expect(screen.getByText('System health')).toBeInTheDocument()
    expect(await screen.findByText('Connected SQLite')).toBeInTheDocument()
    expect(screen.getAllByText('Local Ollama').length).toBeGreaterThan(0)
    expect(screen.getByText('Local Filesystem MCP')).toBeInTheDocument()
    expect(screen.getByText('5 discovered tools')).toBeInTheDocument()
    expect(screen.getByText('fs.read · fs.write')).toBeInTheDocument()
    expect(screen.getByText('Privacy center')).toBeInTheDocument()
  })
})

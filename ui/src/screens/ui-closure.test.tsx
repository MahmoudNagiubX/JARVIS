import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
})

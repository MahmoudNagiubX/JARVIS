import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
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

function apiFor(post: ReturnType<typeof vi.fn>, getOverrides: Record<string, unknown> = {}): ApiClient {
  const get = vi.fn(async (path: string) => {
    if (getOverrides[path] !== undefined) return getOverrides[path]
    if (path === '/experience/state') return baseProjection
    if (path === '/conversations') return { conversations: [] }
    return {}
  })
  return { session: null, setSession: vi.fn(), get, post, patch: vi.fn(), delete: vi.fn() } as unknown as ApiClient
}

describe('Phase 14 residual closure contracts', () => {
  beforeEach(() => { window.location.hash = '#/' })
  afterEach(() => { vi.useRealTimers() })

  it('keeps a running chat active beyond the old 30-second watcher deadline', async () => {
    vi.useFakeTimers()
    window.location.hash = '#/chat'
    const post = vi.fn(async (path: string) => path === '/messages/start'
      ? { run_id: 'run-long', conversation_id: 'conversation-long', state: 'queued' }
      : {})
    const api = apiFor(post, {
      '/conversations/conversation-long/messages': { messages: [] },
      '/runs/run-long': { run_id: 'run-long', conversation_id: 'conversation-long', state: 'running' },
    })
    render(<App api={api} initialSession={session} />)

    fireEvent.change(screen.getByRole('textbox', { name: 'Message JARVIS' }), { target: { value: 'keep watching' } })
    fireEvent.click(screen.getByRole('button', { name: /Send message/ }))
    await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })
    expect(screen.getByRole('button', { name: 'Cancel run' })).toBeEnabled()

    await vi.advanceTimersByTimeAsync(31_000)

    expect(screen.getByRole('button', { name: 'Cancel run' })).toBeEnabled()
    expect(screen.queryByText('The local run did not reach a terminal state.')).not.toBeInTheDocument()
  })

  it('keeps paused runs visible as approval state instead of clearing them', async () => {
    vi.useFakeTimers()
    window.location.hash = '#/chat'
    const post = vi.fn(async (path: string) => path === '/messages/start'
      ? { run_id: 'run-paused', conversation_id: 'conversation-paused', state: 'queued' }
      : {})
    const api = apiFor(post, {
      '/conversations/conversation-paused/messages': { messages: [] },
      '/runs/run-paused': { run_id: 'run-paused', conversation_id: 'conversation-paused', state: 'paused' },
    })
    render(<App api={api} initialSession={session} />)

    fireEvent.change(screen.getByRole('textbox', { name: 'Message JARVIS' }), { target: { value: 'wait for approval' } })
    fireEvent.click(screen.getByRole('button', { name: /Send message/ }))
    await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })

    expect(screen.getByRole('status')).toHaveTextContent('Run paused pending approval.')
    expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument()
  })

  it('refreshes canonical conversation state when a long-running chat eventually succeeds', async () => {
    vi.useFakeTimers()
    window.location.hash = '#/chat'
    let state = 'running'
    const post = vi.fn(async (path: string) => path === '/messages/start'
      ? { run_id: 'run-eventual', conversation_id: 'conversation-eventual', state: 'queued' }
      : {})
    const api = apiFor(post, {
      '/conversations/conversation-eventual/messages': { messages: [] },
    })
    const originalGet = api.get
    api.get = vi.fn(async (path: string) => {
      if (path === '/runs/run-eventual') return { run_id: 'run-eventual', conversation_id: 'conversation-eventual', state }
      if (path === '/conversations/conversation-eventual/messages' && state === 'succeeded') {
        return { messages: [{ id: 'assistant-1', role: 'assistant', content: 'Finished after a long run', run_id: 'run-eventual' }] }
      }
      return originalGet(path)
    }) as unknown as ApiClient['get']
    render(<App api={api} initialSession={session} />)

    fireEvent.change(screen.getByRole('textbox', { name: 'Message JARVIS' }), { target: { value: 'finish eventually' } })
    fireEvent.click(screen.getByRole('button', { name: /Send message/ }))
    await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })
    expect(screen.getByRole('button', { name: 'Cancel run' })).toBeEnabled()
    await vi.advanceTimersByTimeAsync(31_000)

    state = 'succeeded'
    await vi.advanceTimersByTimeAsync(500)

    expect(screen.getByText('Finished after a long run')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument()
    expect(screen.queryByText('The local run did not reach a terminal state.')).not.toBeInTheDocument()
  })

  it('restores approval controls after a failed submit and allows a later decision', async () => {
    window.location.hash = '#/approvals'
    let attempts = 0
    const projection = { ...baseProjection, approvals: [{ approval_id: 'approval-recover', action: 'tool.local.action', status: 'pending', run_id: 'run-recover' }] }
    const post = vi.fn(async () => {
      attempts += 1
      if (attempts === 1) throw new Error('approval endpoint unavailable')
      return {}
    })
    const api = apiFor(post)
    api.get = vi.fn(async (path: string) => path === '/experience/state' ? projection : {}) as unknown as ApiClient['get']
    render(<App api={api} initialSession={session} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.getByText('approval endpoint unavailable')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Deny' })).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: 'Deny' }))
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2))
    expect(post).toHaveBeenLastCalledWith('/approvals/approval-recover', { run_id: 'run-recover', approved: false })
  })
})

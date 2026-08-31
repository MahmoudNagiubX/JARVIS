import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import type { ApiClient, JarvisSession } from '../lib/api'
import type { ExperienceState } from '../lib/events'

const session: JarvisSession = { owner_id: 'owner-1', identity_id: 'identity-1', device_id: 'device-1', csrf_token: 'csrf-1' }
const projection: ExperienceState = {
  system: { runtime_state: 'ready', offline: true, model_available: true, model_alias: 'local-qwen' },
  approvals: [], missions: [], notifications: [], devices: [], goals: [], skills: [], automations: [], timeline: [], presence: {}, home: {}, voice: {},
}

function fakeApi(): ApiClient {
  const get = vi.fn(async (path: string) => {
    if (path === '/experience/state') return projection
    if (path === '/conversations') return { conversations: [] }
    return {}
  })
  return { session: null, setSession: vi.fn(), get, post: vi.fn(), patch: vi.fn(), delete: vi.fn() } as unknown as ApiClient
}

describe('Command Center component surface', () => {
  beforeEach(() => { window.location.hash = '#/' })

  it('renders authoritative home state and navigates to the real chat screen', async () => {
    const api = fakeApi()
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByText('Good to see you.')).toBeInTheDocument()
    expect(screen.getByText('local-qwen')).toBeInTheDocument()
    expect(screen.getByText('Internet is unavailable. Local capabilities remain available.')).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('link', { name: /Chat/ })[0])
    expect(await screen.findByText('Chat with JARVIS')).toBeInTheDocument()
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/conversations'))
  })

  it('keeps an empty production projection explicit rather than rendering fixture data', async () => {
    const api = fakeApi()
    render(<App api={api} initialSession={session} />)
    expect(await screen.findByText('No active missions')).toBeInTheDocument()
    expect(screen.queryByText('Demo mission')).not.toBeInTheDocument()
  })
})

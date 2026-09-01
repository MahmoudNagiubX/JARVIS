import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from '../app/App'
import type { ApiClient, JarvisSession } from '../lib/api'
import type { ExperienceState } from '../lib/events'

const session: JarvisSession = {
  owner_id: 'owner-1',
  identity_id: 'identity-1',
  device_id: 'device-1',
  csrf_token: 'csrf-1',
  expires_at: new Date(Date.now() + 600_000).toISOString(),
}

const baseProjection: ExperienceState = {
  system: { runtime_state: 'ready', offline: true, model_available: true, model_alias: 'local-qwen' },
  approvals: [],
  missions: [],
  notifications: [],
  devices: [],
  goals: [],
  skills: [],
  automations: [],
  timeline: [],
  presence: {},
  home: {},
  voice: {},
}

function apiFor(
  projection: ExperienceState,
  postMock = vi.fn(async () => ({})),
  patchMock = vi.fn(async () => ({})),
  deleteMock = vi.fn(async () => ({})),
  getOverrides: Record<string, unknown> = {}
): ApiClient {
  const get = vi.fn(async (path: string) => {
    if (getOverrides[path] !== undefined) return getOverrides[path]
    if (path === '/experience/state') return projection
    if (path === '/conversations') return { conversations: [] }
    if (path.startsWith('/memory')) {
      const url = new URL(`http://localhost${path}`)
      const cat = url.searchParams.get('category')
      const q = url.searchParams.get('q')
      let allMems = [
        {
          id: 'mem-1',
          category: 'fact',
          content: 'Project Phoenix uses SQLite.',
          source: 'conversation',
          source_reference: 'session-1',
          confidence: 0.95,
          sensitivity: 'personal',
          status: 'active',
          pinned: 0,
          archived: 0,
          tags_json: '["tech", "database"]',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
        {
          id: 'mem-2',
          category: 'preference',
          content: 'Preferred editor is PyCharm.',
          source: 'owner',
          source_reference: 'direct',
          confidence: 1.0,
          sensitivity: 'personal',
          status: 'active',
          pinned: 1,
          archived: 0,
          tags_json: '["editor"]',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ]
      if (cat && cat !== 'all') {
        allMems = allMems.filter((m) => m.category === cat)
      }
      if (q) {
        allMems = allMems.filter((m) => m.content.toLowerCase().includes(q.toLowerCase()))
      }
      return {
        memories: allMems,
      }
    }
    return {}
  })
  return {
    session,
    setSession: vi.fn(),
    get,
    post: postMock,
    patch: patchMock,
    delete: deleteMock,
  } as unknown as ApiClient
}

describe('Phase 16 Frontend Surfaces & Missions / Memory Contracts', () => {
  beforeEach(() => {
    window.location.hash = '#/'
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders MemoryScreen with category filtering, search, and provenance tags', async () => {
    window.location.hash = '#/memory'
    const api = apiFor(baseProjection)
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByText('Project Phoenix uses SQLite.')).toBeInTheDocument()
    expect(screen.getByText('Preferred editor is PyCharm.')).toBeInTheDocument()
    expect(screen.getByText('Owner stated')).toBeInTheDocument()
    expect(screen.getByText('Conversation extracted')).toBeInTheDocument()

    // Filter by category
    const prefTab = screen.getByRole('button', { name: 'Preference' })
    fireEvent.click(prefTab)
    await waitFor(() => {
      expect(screen.getByText('Preferred editor is PyCharm.')).toBeInTheDocument()
      expect(screen.queryByText('Project Phoenix uses SQLite.')).not.toBeInTheDocument()
    })
  })

  it('supports memory search, edit, pin, and delete actions', async () => {
    window.location.hash = '#/memory'
    const patchMock = vi.fn(async () => ({}))
    const postMock = vi.fn(async () => ({}))
    const deleteMock = vi.fn(async () => ({}))
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    const api = apiFor(baseProjection, postMock, patchMock, deleteMock)
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByText('Project Phoenix uses SQLite.')).toBeInTheDocument()

    // Pin / Unpin toggle
    const pinButtons = screen.getAllByRole('button', { name: /Pin|Unpin/ })
    expect(pinButtons.length).toBeGreaterThan(0)
    fireEvent.click(pinButtons[0])
    await waitFor(() => {
      expect(postMock).toHaveBeenCalled()
    })

    // Edit memory
    const editButtons = screen.getAllByRole('button', { name: 'Edit' })
    fireEvent.click(editButtons[0])
    expect(await screen.findByText('Edit memory')).toBeInTheDocument()
    const textarea = screen.getByLabelText('Content')
    fireEvent.change(textarea, { target: { value: 'Project Phoenix uses SQLite and Redis.' } })
    const saveButton = screen.getByRole('button', { name: 'Save memory' })
    fireEvent.click(saveButton)
    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith(
        expect.stringContaining('/memory/'),
        { content: 'Project Phoenix uses SQLite and Redis.' }
      )
    })

    // Delete memory
    const deleteButtons = screen.getAllByRole('button', { name: 'Delete' })
    fireEvent.click(deleteButtons[0])
    await waitFor(() => {
      expect(deleteMock).toHaveBeenCalledWith(
        expect.stringContaining('/memory/'),
        {}
      )
    })
  })

  it('renders MemoryScreen empty state truthfully when no memories match', async () => {
    window.location.hash = '#/memory'
    const api = apiFor(baseProjection, vi.fn(async () => ({})), vi.fn(async () => ({})), vi.fn(async () => ({})), {
      '/memory?limit=50': { memories: [] },
    })
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByText('No memories found')).toBeInTheDocument()
    expect(screen.getByText('Memory remains empty until the canonical MemoryService accepts a record.')).toBeInTheDocument()
  })

  it('renders MissionsScreen with READY mission and triggers start action', async () => {
    window.location.hash = '#/missions'
    const postMock = vi.fn(async () => ({}))
    const projection: ExperienceState = {
      ...baseProjection,
      missions: [
        {
          mission_id: 'mission-ready-1',
          title: 'Deploy Phase 16 Release',
          status: 'ready',
          current_step: 'Step 1: Run tests',
          tool_activity: ['compiler'],
          elapsed: '0s',
        },
      ],
    }
    const api = apiFor(projection, postMock)
    render(<App api={api} initialSession={session} />)

    const titles = await screen.findAllByText('Deploy Phase 16 Release')
    expect(titles.length).toBeGreaterThan(0)
    const startButton = screen.getByRole('button', { name: 'Start' })
    expect(startButton).toBeInTheDocument()

    fireEvent.click(startButton)
    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith('/missions/mission-ready-1/start', {})
    })
  })

  it('provides pause and cancel actions for running missions', async () => {
    window.location.hash = '#/missions'
    const postMock = vi.fn(async () => ({}))
    const projection: ExperienceState = {
      ...baseProjection,
      missions: [
        {
          mission_id: 'mission-running-1',
          title: 'Execute Swarm Tasks',
          status: 'running',
          current_step: 'Step 2: Processing',
          tool_activity: ['runner'],
        },
      ],
    }
    const api = apiFor(projection, postMock)
    render(<App api={api} initialSession={session} />)

    const titles = await screen.findAllByText('Execute Swarm Tasks')
    expect(titles.length).toBeGreaterThan(0)
    const pauseButton = screen.getByRole('button', { name: 'Pause' })
    const cancelButton = screen.getByRole('button', { name: 'Cancel' })
    expect(pauseButton).toBeInTheDocument()
    expect(cancelButton).toBeInTheDocument()

    fireEvent.click(pauseButton)
    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith('/missions/mission-running-1/pause', {})
    })

    fireEvent.click(cancelButton)
    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith('/missions/mission-running-1/cancel', {})
    })
  })

  it('provides resume action for paused or waiting approval missions', async () => {
    window.location.hash = '#/missions'
    const postMock = vi.fn(async () => ({}))
    const projection: ExperienceState = {
      ...baseProjection,
      missions: [
        {
          mission_id: 'mission-paused-1',
          title: 'Paused Deploy Mission',
          status: 'paused',
          current_step: 'Step 2: Awaiting Resume',
        },
        {
          mission_id: 'mission-waiting-1',
          title: 'Awaiting Consequential Approval',
          status: 'waiting_approval',
          current_step: 'Step 3: Apply Migrations',
        },
      ],
    }
    const api = apiFor(projection, postMock)
    render(<App api={api} initialSession={session} />)

    const pausedTitles = await screen.findAllByText('Paused Deploy Mission')
    expect(pausedTitles.length).toBeGreaterThan(0)
    const waitingTitles = await screen.findAllByText('Awaiting Consequential Approval')
    expect(waitingTitles.length).toBeGreaterThan(0)

    const resumeButtons = screen.getAllByRole('button', { name: 'Resume' })
    expect(resumeButtons.length).toBe(2)

    fireEvent.click(resumeButtons[0])
    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith('/missions/mission-paused-1/resume', {})
    })
  })

  it('handles empty states truthfully when no missions exist', async () => {
    window.location.hash = '#/missions'
    const api = apiFor(baseProjection)
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByText('No missions in this view')).toBeInTheDocument()
    expect(screen.getByText('Production state is empty until the canonical mission service creates work.')).toBeInTheDocument()
  })

  it('renders proactive notifications with filtering and dismissal', async () => {
    window.location.hash = '#/notifications'
    const postMock = vi.fn(async () => ({}))
    const projection: ExperienceState = {
      ...baseProjection,
      notifications: [
        {
          notification_id: 'notif-1',
          title: 'Goal Blocked Alert',
          message: 'Milestone 3 is blocked by dependency.',
          severity: 'warning',
          source: 'proactive.goal_blocked',
          created_at: '2026-01-01T00:00:00Z',
          dismissed: 0,
        },
        {
          notification_id: 'notif-2',
          title: 'System Online',
          message: 'Local runtime started.',
          severity: 'info',
          source: 'system',
          created_at: '2026-01-01T00:00:00Z',
          dismissed: 0,
        },
      ],
    }
    const api = apiFor(projection, postMock)
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByText('Goal Blocked Alert')).toBeInTheDocument()
    expect(screen.getByText('System Online')).toBeInTheDocument()

    // Filter to Proactive
    const proactiveTab = screen.getByRole('button', { name: 'Proactive' })
    fireEvent.click(proactiveTab)
    expect(screen.getByText('Goal Blocked Alert')).toBeInTheDocument()
    expect(screen.queryByText('System Online')).not.toBeInTheDocument()

    // Dismiss notification
    const dismissButton = screen.getByRole('button', { name: 'Dismiss' })
    fireEvent.click(dismissButton)
    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith('/notifications/notif-1/dismiss', {})
    })
  })

  it('renders Privacy and Settings truth without cloud dependencies or surveillance', async () => {
    window.location.hash = '#/settings'
    const api = apiFor(baseProjection)
    render(<App api={api} initialSession={session} />)

    expect(await screen.findByText('Privacy center')).toBeInTheDocument()
    expect(screen.getByText('Local brain')).toBeInTheDocument()
    expect(screen.getByText('Raw audio stored')).toBeInTheDocument()
    expect(screen.getByText('Core cloud dependency')).toBeInTheDocument()
  })
})

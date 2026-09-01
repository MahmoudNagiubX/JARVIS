import { describe, expect, it } from 'vitest'
import { deriveVisualState } from './deriveVisualState'
import type { ExperienceState } from '../../lib/events'

function projection(overrides: Partial<ExperienceState> = {}): ExperienceState {
  return {
    system: { runtime_state: 'ready', model_available: true },
    approvals: [],
    missions: [],
    notifications: [],
    devices: [],
    ...overrides,
  }
}

describe('deriveVisualState', () => {
  it('starts in offline mode without inventing a runtime state', () => {
    expect(deriveVisualState(null)).toBe('offline')
  })

  it('maps an owner approval checkpoint before lower-priority activity', () => {
    expect(deriveVisualState(projection({ approvals: [{ approval_id: 'a1', status: 'pending' }], missions: [{ status: 'running' }] }))).toBe('waiting_approval')
  })

  it('maps canonical voice and run states to presentation states', () => {
    expect(deriveVisualState(projection({ voice: { state: 'speaking' } }))).toBe('speaking')
    expect(deriveVisualState(projection({ operations: { state: 'tool_running' } }))).toBe('tool')
    expect(deriveVisualState(projection({ research: [{ status: 'running' }] }))).toBe('researching')
    expect(deriveVisualState(projection({ system: { runtime_state: 'processing' } }))).toBe('thinking')
  })

  it('maps degraded and hard failures without green-state assumptions', () => {
    expect(deriveVisualState(projection({ system: { runtime_state: 'degraded' } }))).toBe('degraded')
    expect(deriveVisualState(projection({ system: { runtime_state: 'error' } }))).toBe('error')
  })
})

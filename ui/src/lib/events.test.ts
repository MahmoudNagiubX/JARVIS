import { describe, expect, it } from 'vitest'
import { normalizeExperienceEvent, reconcileProjection, type ExperienceState } from './events'

const projection: ExperienceState = {
  system: { runtime_state: 'ready', offline: true, model_available: true },
  approvals: [],
  missions: [],
  notifications: [],
  devices: [],
}

describe('experience stream adapter', () => {
  it('accepts the canonical state envelope and rejects unrelated payloads', () => {
    expect(normalizeExperienceEvent({ type: 'state', data: projection })).toEqual({ kind: 'snapshot', data: projection })
    expect(normalizeExperienceEvent({ type: 'event', data: { event_type: 'secret.raw' } })).toEqual({ kind: 'event', data: { event_type: 'secret.raw' } })
    expect(normalizeExperienceEvent({ type: 'unknown', data: {} })).toBeNull()
  })

  it('reconciles a fresh snapshot and preserves the server as the source of truth', () => {
    const next: ExperienceState = { ...projection, system: { ...projection.system, runtime_state: 'degraded' } }
    expect(reconcileProjection(projection, { kind: 'snapshot', data: next })).toEqual(next)
    expect(reconcileProjection(projection, { kind: 'event', data: { event_type: 'ui.local.fake' } })).toEqual(projection)
  })
})

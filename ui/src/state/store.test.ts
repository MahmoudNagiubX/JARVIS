import { describe, expect, it } from 'vitest'
import { initialUiState, uiReducer } from './store'

describe('browser UI state', () => {
  it('keeps loading/error state separate from authoritative projection data', () => {
    const loading = uiReducer(initialUiState, { type: 'loading', value: true })
    const errored = uiReducer(loading, { type: 'error', value: 'local runtime unavailable' })

    expect(loading.loading).toBe(true)
    expect(errored.error).toBe('local runtime unavailable')
    expect(errored.projection).toBeNull()
  })

  it('reconciles a server projection and clears stale errors', () => {
    const next = uiReducer(
      { ...initialUiState, error: 'stale' },
      { type: 'projection', value: { system: { runtime_state: 'ready' }, approvals: [], missions: [], notifications: [], devices: [] } },
    )
    expect(next.projection?.system.runtime_state).toBe('ready')
    expect(next.error).toBe('')
  })
})

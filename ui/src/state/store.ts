import type { ExperienceState } from '../lib/events'

export interface UiState {
  loading: boolean
  error: string
  projection: ExperienceState | null
}

export const initialUiState: UiState = {
  loading: true,
  error: '',
  projection: null,
}

export type UiAction =
  | { type: 'loading'; value: boolean }
  | { type: 'error'; value: string }
  | { type: 'projection'; value: ExperienceState }

export function uiReducer(state: UiState, action: UiAction): UiState {
  switch (action.type) {
    case 'loading': return { ...state, loading: action.value }
    case 'error': return { ...state, error: action.value }
    case 'projection': return { ...state, projection: action.value, error: '' }
    default: return state
  }
}

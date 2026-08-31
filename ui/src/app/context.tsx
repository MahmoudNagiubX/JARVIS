import { createContext, useContext } from 'react'
import type { ApiClient, JarvisSession } from '../lib/api'
import type { ExperienceState } from '../lib/events'
import type { JsonRecord } from '../lib/format'

export interface ScreenData {
  conversations: JsonRecord[]
  messages: JsonRecord[]
  memories: JsonRecord[]
  research: JsonRecord[]
  context: JsonRecord
  health: JsonRecord
  profile: JsonRecord
}

export const emptyScreenData: ScreenData = {
  conversations: [], messages: [], memories: [], research: [], context: {}, health: {}, profile: {},
}

export interface AppContextValue {
  api: ApiClient
  session: JarvisSession | null
  projection: ExperienceState | null
  screenData: ScreenData
  loading: boolean
  screenLoading: boolean
  error: string
  streamState: 'live' | 'snapshot' | 'reconnecting' | 'unavailable'
  refreshProjection(): Promise<void>
  refreshScreen(path?: string): Promise<void>
  setScreenData(patch: Partial<ScreenData>): void
  setError(message: string): void
}

export const AppContext = createContext<AppContextValue | null>(null)

export function useJarvis(): AppContextValue {
  const value = useContext(AppContext)
  if (!value) throw new Error('useJarvis must be used inside the Command Center')
  return value
}

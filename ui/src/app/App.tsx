import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { HashRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { createApiClient, type ApiClient, type JarvisSession } from '../lib/api'
import { normalizeExperienceEvent, reconcileProjection, type ExperienceState } from '../lib/events'
import { list, record } from '../lib/format'
import { AppContext, emptyScreenData, type ScreenData } from './context'
import { AppShell } from '../components/layout/AppShell'
import { ErrorBoundary } from '../components/common/ErrorBoundary'
import { initialUiState, uiReducer } from '../state/store'
import { ActivityScreen, ApprovalsScreen, BrowserScreen, ChatScreen, ContextScreen, DevicesScreen, EngineeringScreen, HomeScreen, MemoryScreen, MissionsScreen, NotificationsScreen, OperationsScreen, ResearchScreen, SettingsScreen, SkillsScreen } from '../screens/Screens'

export interface AppProps {
  api?: ApiClient
  initialSession?: JarvisSession
}

async function bootstrapSession(api: ApiClient, initialSession?: JarvisSession): Promise<JarvisSession> {
  if (initialSession) { api.setSession(initialSession); return initialSession }
  const match = window.location.hash.match(/(?:^#\/?|[?&])bootstrap=([^&]+)/)
  const session = match ? await api.post<JarvisSession>('/auth/desktop-session', { bootstrap: decodeURIComponent(match[1]) }) : await api.get<JarvisSession>('/auth/session')
  api.setSession(session)
  if (match) window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`)
  return session
}

function Workspace({ api, initialSession }: { api: ApiClient; initialSession?: JarvisSession }) {
  const location = useLocation()
  const [ui, dispatch] = useReducer(uiReducer, initialUiState)
  const [session, setSession] = useState<JarvisSession | null>(initialSession || null)
  const [screenData, setScreenDataState] = useState<ScreenData>(emptyScreenData)
  const [screenLoading, setScreenLoading] = useState(false)
  const [streamState, setStreamState] = useState<'live' | 'snapshot' | 'reconnecting' | 'unavailable'>(initialSession ? 'snapshot' : 'unavailable')
  const projectionRef = useRef<ExperienceState | null>(null)
  projectionRef.current = ui.projection

  const setError = useCallback((message: string) => dispatch({ type: 'error', value: message }), [])
  const refreshProjection = useCallback(async () => {
    const projection = await api.get<ExperienceState>('/experience/state')
    dispatch({ type: 'projection', value: projection })
  }, [api])
  const refreshScreen = useCallback(async (path = location.pathname) => {
    setScreenLoading(true)
    try {
      if (path === '/chat') {
        const payload = await api.get<{ conversations?: unknown[] }>('/conversations')
        setScreenDataState((current) => ({ ...current, conversations: list(payload.conversations) }))
      } else if (path === '/memory') {
        const payload = await api.get<{ memories?: unknown[] }>('/memory?limit=50')
        setScreenDataState((current) => ({ ...current, memories: list(payload.memories) }))
      } else if (path === '/context') {
        const payload = await api.get<Record<string, unknown>>('/context')
        setScreenDataState((current) => ({ ...current, context: record(payload) }))
      } else if (path === '/research') {
        const payload = await api.get<{ runs?: unknown[] }>('/research/runs')
        setScreenDataState((current) => ({ ...current, research: list(payload.runs) }))
      } else if (path === '/settings') {
        const [health, profile] = await Promise.all([api.get<Record<string, unknown>>('/health'), api.get<Record<string, unknown>>('/personalization/profile')])
        setScreenDataState((current) => ({ ...current, health: record(health), profile: record(profile) }))
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : 'The local screen could not be loaded.')
    } finally { setScreenLoading(false) }
  }, [api, location.pathname, setError])

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        dispatch({ type: 'loading', value: true })
        const currentSession = await bootstrapSession(api, initialSession)
        if (!active) return
        setSession(currentSession)
        await refreshProjection()
        if (active) dispatch({ type: 'loading', value: false })
      } catch (error) {
        if (!active) return
        dispatch({ type: 'loading', value: false })
        setError(error instanceof Error ? error.message : 'The local session could not be established.')
      }
    })()
    return () => { active = false }
  }, [api, initialSession, refreshProjection, setError])

  useEffect(() => { if (!ui.loading && session) void refreshScreen(location.pathname) }, [location.pathname, refreshScreen, session, ui.loading])

  useEffect(() => {
    if (!session || typeof WebSocket === 'undefined') return
    let disposed = false
    let socket: WebSocket | null = null
    let retry: number | undefined
    const connect = () => {
      if (disposed) return
      setStreamState('reconnecting')
      const url = new URL('/v1/experience/events/ws?topic=system_health', window.location.href)
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      try { socket = new WebSocket(url.toString()) } catch { setStreamState('unavailable'); retry = window.setTimeout(connect, 5000); return }
      socket.onopen = () => setStreamState('live')
      socket.onmessage = (event) => {
        try {
          const message = normalizeExperienceEvent(JSON.parse(event.data))
          if (!message) return
          const next = reconcileProjection(projectionRef.current, message)
          if (next && message.kind === 'snapshot') dispatch({ type: 'projection', value: next })
          if (message.kind === 'event') window.setTimeout(() => { if (!disposed) void refreshProjection() }, 250)
        } catch { setStreamState('unavailable') }
      }
      socket.onerror = () => setStreamState('reconnecting')
      socket.onclose = () => { if (!disposed) { setStreamState('reconnecting'); retry = window.setTimeout(() => { void refreshProjection().finally(connect) }, 5000) } }
    }
    connect()
    return () => { disposed = true; if (retry) window.clearTimeout(retry); socket?.close() }
  }, [session, refreshProjection])

  const setScreenData = useCallback((patch: Partial<ScreenData>) => setScreenDataState((current) => ({ ...current, ...patch })), [])
  const value = useMemo(() => ({ api, session, projection: ui.projection, screenData, loading: ui.loading, screenLoading, error: ui.error, streamState, refreshProjection, refreshScreen, setScreenData, setError }), [api, session, ui.projection, screenData, ui.loading, screenLoading, ui.error, streamState, refreshProjection, refreshScreen, setScreenData, setError])
  if (!session && ui.loading) return <div className="boot-screen"><div className="boot-orb"><i /></div><span>Establishing the local owner session…</span></div>
  if (!session && !ui.loading) return <div className="fatal-screen"><div className="boot-orb"><i /></div><h1>JARVIS is waiting for a local session</h1><p>{ui.error || 'Open the Command Center from the desktop launcher.'}</p></div>
  return <AppContext.Provider value={value}><ErrorBoundary><AppShell><Routes>
    <Route path="/" element={<HomeScreen />} /><Route path="/chat" element={<ChatScreen />} /><Route path="/missions" element={<MissionsScreen />} /><Route path="/memory" element={<MemoryScreen />} /><Route path="/context" element={<ContextScreen />} /><Route path="/operations" element={<OperationsScreen />} /><Route path="/research" element={<ResearchScreen />} /><Route path="/engineering" element={<EngineeringScreen />} /><Route path="/browser" element={<BrowserScreen />} /><Route path="/skills" element={<SkillsScreen />} /><Route path="/devices" element={<DevicesScreen />} /><Route path="/notifications" element={<NotificationsScreen />} /><Route path="/approvals" element={<ApprovalsScreen />} /><Route path="/activity" element={<ActivityScreen />} /><Route path="/settings" element={<SettingsScreen />} /><Route path="*" element={<Navigate to="/" replace />} />
  </Routes></AppShell></ErrorBoundary></AppContext.Provider>
}

export function App({ api = createApiClient(), initialSession }: AppProps) {
  return <HashRouter><Workspace api={api} initialSession={initialSession} /></HashRouter>
}

import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useJarvis } from '../app/context'
import { JArcReactor } from '../components/hud/JArcReactor'
import { JHudFrame } from '../components/hud/JHudFrame'
import { JWaveform } from '../components/hud/JWaveform'
import { Button, DetailList, EmptyState, FramePanel, ListCard, LoadingState, Metric, Panel, SectionHeading, StatusBadge } from '../components/common/Primitives'
import { eventLabel } from '../lib/events'
import { dateValue, list, record, shortDate, statusText, stringValue, tone } from '../lib/format'
import type { JsonRecord } from '../lib/format'

function projectionList(projection: Record<string, unknown> | null, key: string): JsonRecord[] {
  return list(projection?.[key])
}

function projectionRecord(projection: Record<string, unknown> | null, key: string): JsonRecord {
  return record(projection?.[key])
}

export function evidenceFromPayload(payload: unknown): unknown[] {
  return list(record(payload).evidence)
}

export type NotificationFilter = 'all' | 'unread' | 'important' | 'proactive' | 'system'

export function filterNotifications(notifications: JsonRecord[], filter: NotificationFilter): JsonRecord[] {
  if (filter === 'all') return notifications
  if (filter === 'unread') return notifications.filter((item) => !Boolean(item.dismissed || item.dismissed_at))
  if (filter === 'important') return notifications.filter((item) => Boolean(item.important) || ['important', 'urgent', 'critical'].includes(stringValue(item.severity).toLowerCase()))
  if (filter === 'proactive') return notifications.filter((item) => stringValue(item.source).toLowerCase().startsWith('proactive'))
  return notifications.filter((item) => stringValue(item.source).toLowerCase().startsWith('system'))
}

export function sessionRefreshDelay(expiresAt?: string, now: Date = new Date()): number | null {
  if (!expiresAt) return null
  const expires = Date.parse(expiresAt)
  if (!Number.isFinite(expires)) return null
  return Math.max(1_000, expires - now.getTime() - 60_000)
}

export function isApprovalActionable(approval: JsonRecord): boolean {
  return stringValue(approval.status, 'pending') === 'pending' && Boolean(stringValue(approval.run_id || approval.pending_run_id, ''))
}

type ActiveRun = { runId: string; conversationId: string; state: string }

function ApprovalCard({ approval, onDecision, interactive }: { approval: JsonRecord; onDecision: (approval: JsonRecord, approved: boolean) => Promise<void>; interactive?: boolean }) {
  const location = useLocation()
  const [deciding, setDeciding] = useState(false)
  const actionsEnabled = interactive ?? location.pathname === '/approvals'
  const id = stringValue(approval.approval_id || approval.id, 'unknown approval')
  const runId = stringValue(approval.run_id || approval.pending_run_id, '')
  const status = stringValue(approval.status, 'pending')
  async function decide(approved: boolean) {
    setDeciding(true)
    try { await onDecision(approval, approved) } finally { setDeciding(false) }
  }
  return <ListCard title={stringValue(approval.action, 'Consequential action')} status={status} meta={`Approval ${id}`}>
    <p className="card-copy">{stringValue(approval.reason, 'The action requires owner confirmation.')}</p>
    {Boolean(approval.preview) && <div className="safe-preview"><span className="eyebrow">SANITIZED PREVIEW</span><p>{stringValue(approval.preview)}</p></div>}
    {status === 'pending' && actionsEnabled && <div className="card-actions inline"><Button variant="primary" disabled={!isApprovalActionable(approval) || deciding} onClick={() => void decide(true)} title={!runId ? 'Waiting for the server run correlation' : undefined}>{deciding ? 'Saving…' : 'Approve'}</Button><Button variant="danger" disabled={!isApprovalActionable(approval) || deciding} onClick={() => void decide(false)}>Deny</Button>{!runId && <span className="small muted">Awaiting run correlation</span>}</div>}
  </ListCard>
}

export function HomeScreen() {
  const { projection, refreshProjection } = useJarvis()
  const state = record(projection)
  const system = projectionRecord(state, 'system')
  const voice = projectionRecord(state, 'voice')
  const presence = projectionRecord(state, 'presence')
  const home = projectionRecord(state, 'home')
  const missions = projectionList(state, 'missions')
  const approvals = projectionList(state, 'approvals').filter((item) => stringValue(item.status, 'pending') === 'pending')
  const timeline = projectionList(state, 'timeline').slice(-6).reverse()
  const ready = stringValue(system.runtime_state, '') === 'ready'
  return <div className="screen"><SectionHeading eyebrow="COMMAND CENTER" title="Good to see you." description="One coherent view of your local JARVIS runtime, current work, and attention queue." action={<Link className="button primary" to="/chat">New chat <span>↗</span></Link>} />
    <div className="hero-layout"><JHudFrame label="JARVIS · CORE STATUS" live={ready}><div className="core-visual"><JArcReactor level={ready ? 100 : 0} color={ready ? 'cyan' : 'amber'} label={statusText(system.runtime_state || 'starting')} animated={ready} /><div><span className="eyebrow">LOCAL BRAIN</span><h2>{stringValue(system.model_alias, system.model_available ? 'Model ready' : 'Model unavailable')}</h2><p className="lede">{system.offline ? 'Internet is unavailable. Local capabilities remain available.' : 'Runtime connected to the local application boundary.'}</p><JWaveform active={stringValue(voice.state, '') === 'listening' || stringValue(voice.state, '') === 'speaking'} /></div></div></JHudFrame><FramePanel title="Runtime status" eyebrow="AUTHORITATIVE HEALTH" status={system.offline ? 'local' : 'online'}><div className="metric-grid"><Metric label="Local brain" value={system.model_available ? 'READY' : 'UNAVAILABLE'} status={system.model_available ? 'ready' : 'unavailable'} /><Metric label="Voice" value={statusText(voice.state || 'sleeping')} status={voice.state} /><Metric label="Devices" value={projectionList(state, 'devices').length} /><Metric label="Approvals" value={approvals.length} status={approvals.length ? 'pending' : 'ready'} /></div><DetailList values={{ Runtime: statusText(system.runtime_state), Provider: stringValue(system.model_provider, 'Not reported'), Network: system.offline ? 'Offline · local features remain available' : 'Online', Generated: dateValue(projection?.generated_at) }} /></FramePanel></div>
    <div className="screen-grid three"><FramePanel title="What needs attention" eyebrow="OWNER QUEUE" status={approvals.length ? 'pending' : 'clear'}>{approvals.length ? <div className="stack">{approvals.slice(0, 2).map((approval) => <ApprovalCard key={stringValue(approval.approval_id || approval.id)} approval={approval} onDecision={async () => undefined} />)}<Link className="text-link" to="/approvals">Open approval center →</Link></div> : <EmptyState title="No pending approvals" detail="Consequential actions will appear here with a sanitized preview." />}</FramePanel><FramePanel title="Current context" eyebrow="FRESH PROJECTION"><DetailList values={{ 'Active app': stringValue(presence.active_application || presence.active_app, 'Not observed'), 'Focused window': stringValue(presence.focused_window, 'Not observed'), Workspace: stringValue(presence.current_workspace, 'Not observed'), Home: home.available ? 'Connected' : 'No live controller' }} /><Link className="text-link" to="/context">Inspect current context →</Link></FramePanel><FramePanel title="Active work" eyebrow="MISSION SERVICE" status={missions.length ? 'active' : 'idle'}>{missions.length ? <div className="compact-list">{missions.slice(0, 4).map((mission) => <div className="compact-row" key={stringValue(mission.mission_id || mission.id)}><div><strong>{stringValue(mission.title || mission.request, 'Untitled mission')}</strong><span>{stringValue(mission.current_step, 'No active step')}</span></div><StatusBadge value={mission.status} /></div>)}</div> : <EmptyState title="No active missions" detail="Create bounded work through the canonical mission service." />}<Link className="text-link" to="/missions">Open missions →</Link></FramePanel></div>
    <div className="screen-grid two"><FramePanel title="Recent activity" eyebrow="EVENT PROJECTION"><ActivityList events={timeline} /><Link className="text-link" to="/activity">View complete timeline →</Link></FramePanel><FramePanel title="Quick health" eyebrow="LOCAL-FIRST"><DetailList values={{ Goals: projectionList(state, 'goals').length, Memory: 'Inspectable', Research: projectionList(state, 'research').length, 'Voice acceptance': 'Deferred by design' }} /><button className="text-link button-link" onClick={() => void refreshProjection()}>Refresh projection ↻</button></FramePanel></div>
  </div>
}

function ActivityList({ events, limit = 100 }: { events: JsonRecord[]; limit?: number }) {
  const values = events.slice(-limit).reverse()
  return values.length ? <div className="activity-list">{values.map((event, index) => <div className="activity-row" key={stringValue(event.event_id, `${event.timestamp}-${index}`)}><time>{shortDate(event.timestamp)}</time><span className={`activity-marker ${tone(event.severity)}`} /><div><strong>{eventLabel(event)}</strong><span>{statusText(event.state || event.category || 'recorded')}</span></div></div>)}</div> : <EmptyState title="No activity yet" detail="Real runtime events will appear here." />
}

export function ChatScreen() {
  const { api, screenData, screenLoading, setScreenData, setError, refreshProjection } = useJarvis()
  const [selected, setSelected] = useState('')
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [activeRun, setActiveRun] = useState<ActiveRun | null>(null)
  const [messageError, setMessageError] = useState('')
  const [activities, setActivities] = useState<Record<string, JsonRecord[]>>({})
  const conversation = screenData.conversations.find((item) => item.id === selected)

  useEffect(() => {
    if (!selected) { setScreenData({ messages: [] }); return }
    void api.get<{ messages?: unknown[] }>(`/conversations/${encodeURIComponent(selected)}/messages`).then((payload) => setScreenData({ messages: list(payload.messages) })).catch((error) => setMessageError(error instanceof Error ? error.message : 'Conversation history unavailable.'))
  }, [api, selected, setScreenData])

  useEffect(() => {
    const runIds = [...new Set(screenData.messages.map((message) => stringValue(message.run_id, '')).filter(Boolean))]
    if (!runIds.length) { setActivities({}); return }
    void Promise.all(runIds.map(async (runId) => [runId, list((await api.get<{ tools?: unknown[] }>(`/runs/${encodeURIComponent(runId)}/activity`)).tools)] as const))
      .then((entries) => setActivities(Object.fromEntries(entries)))
      .catch((error) => setMessageError(error instanceof Error ? error.message : 'Run activity unavailable.'))
  }, [api, screenData.messages])

  async function refreshConversation(conversationId: string) {
    const [history, conversations] = await Promise.all([
      api.get<{ messages?: unknown[] }>(`/conversations/${encodeURIComponent(conversationId)}/messages`),
      api.get<{ conversations?: unknown[] }>('/conversations'),
    ])
    setScreenData({ messages: list(history.messages), conversations: list(conversations.conversations) })
    await refreshProjection()
  }

  useEffect(() => {
    if (!activeRun) return
    let disposed = false
    let timer: number | undefined
    const terminalStates = new Set(['succeeded', 'failed', 'cancelled'])
    const reconcile = async () => {
      try {
        const status = await api.get<JsonRecord>(`/runs/${encodeURIComponent(activeRun.runId)}`)
        if (disposed) return
        const state = stringValue(status.state, 'running')
        setActiveRun((current) => current?.runId === activeRun.runId ? { ...current, state } : current)
        if (terminalStates.has(state)) {
          await refreshConversation(activeRun.conversationId)
          if (disposed) return
          setActiveRun((current) => current?.runId === activeRun.runId ? null : current)
          setSending(false)
          return
        }
        if (state === 'paused') setSending(false)
        timer = window.setTimeout(() => void reconcile(), 200)
      } catch {
        if (!disposed) timer = window.setTimeout(() => void reconcile(), 500)
      }
    }
    void reconcile()
    return () => { disposed = true; if (timer) window.clearTimeout(timer) }
  }, [activeRun?.runId, api])

  async function send(event: React.FormEvent) {
    event.preventDefault(); const text = draft.trim(); if (!text || sending) return
    setSending(true); setMessageError('')
    try {
      const result = await api.post<JsonRecord>('/messages/start', { text, conversation_id: selected || undefined, client_message_id: `ui-${globalThis.crypto?.randomUUID?.() || Date.now()}` })
      const conversationId = stringValue(result.conversation_id, selected)
      const runId = stringValue(result.run_id, '')
      setSelected(conversationId)
      if (runId) setActiveRun({ runId, conversationId, state: stringValue(result.state, 'queued') })
      setDraft('')
      await refreshConversation(conversationId)
      if (!runId) setSending(false)
    } catch (error) { setSending(false); setMessageError(error instanceof Error ? error.message : 'Message failed.') }
  }

  async function cancel() {
    if (!activeRun?.runId) return
    try { await api.post(`/runs/${encodeURIComponent(activeRun.runId)}/cancel`) } catch (error) { setError(error instanceof Error ? error.message : 'Run cancellation failed.') }
  }

  return <div className="screen"><SectionHeading eyebrow="CONVERSATION" title="Chat with JARVIS" description="The text path reaches the same local AgentRuntime, context, tools, permissions, and approvals." /><div className="chat-layout"><Panel className="conversation-panel"><div className="panel-head"><div><span className="eyebrow">HISTORY</span><h2>Conversations</h2></div><Button variant="quiet" onClick={() => { setSelected(''); setScreenData({ messages: [] }) }}>New</Button></div>{screenLoading ? <LoadingState label="Loading conversations…" /> : screenData.conversations.length ? <div className="conversation-list">{screenData.conversations.map((item) => <button className={`conversation-row ${selected === item.id ? 'active' : ''}`} key={stringValue(item.id)} onClick={() => setSelected(stringValue(item.id))}><strong>{stringValue(item.title, 'Untitled conversation')}</strong><span>{shortDate(item.updated_at || item.last_message_at)}</span></button>)}</div> : <EmptyState title="No saved conversations" detail="Your first message creates one." />}</Panel><Panel className="chat-panel"><div className="panel-head"><div><span className="eyebrow">LOCAL AGENT RUNTIME</span><h2>{conversation ? stringValue(conversation.title, 'Conversation') : 'New conversation'}</h2></div><StatusBadge value={activeRun?.state === 'paused' ? 'approval' : sending ? 'processing' : 'ready'} /></div>{messageError && <div className="inline-error" role="alert">{messageError}</div>}{activeRun?.state === 'paused' && <div className="notice" role="status">Run paused pending approval.</div>}<div className="message-list" aria-live="polite">{screenData.messages.length ? screenData.messages.map((message, index) => <article className={`message ${message.role === 'user' ? 'user' : 'assistant'}`} key={stringValue(message.message_id || message.id, `${message.created_at}-${index}`)}><span className="message-role">{message.role === 'user' ? 'YOU' : 'JARVIS'}</span><p>{stringValue(message.content, '')}</p><time>{dateValue(message.created_at)}</time>{list(activities[stringValue(message.run_id, '')]).map((tool, toolIndex) => <div className="tool-inline" key={`${toolIndex}-${stringValue(tool.name)}`}><span className="tool-dot" />{stringValue(tool.name || tool.tool, 'Tool activity')} <StatusBadge value={tool.status} /></div>)}</article>) : <EmptyState title="Start a conversation" detail="Ask a normal question and the local model will answer through the canonical runtime." />}{sending && <div className="message assistant pending-message"><span className="message-role">JARVIS</span><p>Working from the local runtime…</p><JWaveform active /></div>}</div><form className="composer" onSubmit={send}><textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ask JARVIS anything local…" aria-label="Message JARVIS" rows={3} required /><div className="composer-footer"><span className="muted small">Enter a message · no cloud provider</span><div>{activeRun && activeRun.state !== 'paused' && <Button variant="quiet" onClick={() => void cancel()}>Cancel run</Button>}<Button variant="primary" type="submit" disabled={sending || !draft.trim()}>{sending ? 'Processing…' : 'Send message ↗'}</Button></div></div></form></Panel></div></div>
}

export function MissionsScreen() {
  const { api, projection, refreshProjection, setError } = useJarvis(); const missions = projectionList(record(projection), 'missions'); const [title, setTitle] = useState(''); const [creating, setCreating] = useState(false); const [filter, setFilter] = useState('all')
  const filtered = missions.filter((item) => filter === 'all' || stringValue(item.status) === filter)
  async function create(event: React.FormEvent) { event.preventDefault(); if (!title.trim()) return; setCreating(true); try { await api.post('/missions', { title: title.trim(), request: title.trim(), plan: true }); setTitle(''); await refreshProjection() } catch (error) { setError(error instanceof Error ? error.message : 'Mission creation failed.') } finally { setCreating(false) } }
  async function action(item: JsonRecord, name: string) { try { await api.post(`/missions/${encodeURIComponent(stringValue(item.mission_id || item.id))}/${name}`, {}) ; await refreshProjection() } catch (error) { setError(error instanceof Error ? error.message : 'Mission action failed.') } }
  return <div className="screen"><SectionHeading eyebrow="OPERATIONS" title="Missions & goals" description="Bounded work already owned by the canonical mission and goal services." /><Panel className="toolbar-panel"><div className="filter-tabs">{['all', 'active', 'scheduled', 'waiting_approval', 'paused', 'completed', 'failed'].map((item) => <button className={filter === item ? 'selected' : ''} key={item} onClick={() => setFilter(item)}>{item === 'all' ? 'All' : statusText(item)}</button>)}</div><form className="inline-form" onSubmit={create}><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Create a bounded mission…" aria-label="Mission title" /><Button variant="primary" type="submit" disabled={creating || !title.trim()}>{creating ? 'Creating…' : 'Create mission'}</Button></form></Panel><div className="screen-grid two">{filtered.length ? filtered.map((item) => <ListCard key={stringValue(item.mission_id || item.id)} title={stringValue(item.title || item.request, 'Untitled mission')} status={item.status} meta={`Updated ${dateValue(item.updated_at)}`}><DetailList values={{ Goal: stringValue(item.goal_id, 'None'), 'Current step': stringValue(item.current_step, 'Not started'), 'Tool activity': list(item.tool_activity).length || 'Not reported', 'Elapsed': stringValue(item.elapsed, 'Not reported') }} />{['draft', 'planned', 'paused'].includes(stringValue(item.status)) && <div className="card-actions inline"><Button onClick={() => void action(item, 'start')}>Start</Button>{stringValue(item.status) === 'paused' && <Button onClick={() => void action(item, 'resume')}>Resume</Button>}</div>}{['running', 'active'].includes(stringValue(item.status)) && <div className="card-actions inline"><Button onClick={() => void action(item, 'pause')}>Pause</Button><Button variant="danger" onClick={() => void action(item, 'cancel')}>Cancel</Button></div>}</ListCard>) : <Panel><EmptyState title="No missions in this view" detail="Production state is empty until the canonical mission service creates work." /></Panel>}</div></div>
}

export function MemoryScreen() {
  const { api, screenData, screenLoading, setScreenData, setError } = useJarvis(); const [query, setQuery] = useState(''); const [editing, setEditing] = useState<JsonRecord | null>(null); const [content, setContent] = useState('')
  async function search(event?: React.FormEvent) { event?.preventDefault(); try { const payload = await api.get<{ memories?: unknown[] }>(`/memory?limit=50${query.trim() ? `&q=${encodeURIComponent(query.trim())}` : ''}`); setScreenData({ memories: list(payload.memories) }) } catch (error) { setError(error instanceof Error ? error.message : 'Memory search failed.') } }
  async function save(event: React.FormEvent) { event.preventDefault(); if (!editing || !content.trim()) return; try { await api.patch(`/memory/${encodeURIComponent(stringValue(editing.memory_id || editing.id))}`, { content: content.trim() }); setEditing(null); await search() } catch (error) { setError(error instanceof Error ? error.message : 'Memory update failed.') } }
  async function remove(item: JsonRecord) { if (!window.confirm('Delete this memory through the canonical MemoryService?')) return; try { await api.delete(`/memory/${encodeURIComponent(stringValue(item.memory_id || item.id))}`, {}); await search() } catch (error) { setError(error instanceof Error ? error.message : 'Memory deletion failed.') } }
  return <div className="screen"><SectionHeading eyebrow="PERSONAL KNOWLEDGE" title="Memory center" description="Inspect durable accepted knowledge. Fresh world observations remain separate from memory." /><Panel className="toolbar-panel"><form className="search-form" onSubmit={(event) => void search(event)}><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search memories by text, type, or source…" aria-label="Search memories" /><Button variant="primary" type="submit">Search</Button></form></Panel>{screenLoading ? <LoadingState /> : <div className="screen-grid two">{screenData.memories.length ? screenData.memories.map((item) => <ListCard key={stringValue(item.memory_id || item.id)} title={stringValue(item.content, 'Empty memory')} meta={`${stringValue(item.category, 'memory')} · ${shortDate(item.updated_at || item.created_at)}`}><DetailList values={{ Source: stringValue(item.source || item.source_reference, 'Unknown'), Confidence: item.confidence ?? 'Not reported', Sensitivity: stringValue(item.sensitivity, 'Not reported'), Validity: stringValue(item.validity, 'Not reported') }} /><div className="card-actions inline"><Button onClick={() => { setEditing(item); setContent(stringValue(item.content, '')) }}>Edit</Button><Button variant="danger" onClick={() => void remove(item)}>Delete</Button></div></ListCard>) : <Panel><EmptyState title="No memories found" detail="Memory remains empty until the canonical MemoryService accepts a record." /></Panel>}</div>}{editing && <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setEditing(null)}><Panel className="modal" as="div"><div className="panel-head"><h2>Edit memory</h2><button className="icon-button" onClick={() => setEditing(null)} aria-label="Close memory editor">×</button></div><form onSubmit={save}><label className="field-label" htmlFor="memory-content">Content</label><textarea id="memory-content" value={content} onChange={(event) => setContent(event.target.value)} rows={7} required /><div className="card-actions inline"><Button variant="primary" type="submit">Save memory</Button><Button onClick={() => setEditing(null)}>Cancel</Button></div></form></Panel></div>}</div>
}

export function ContextScreen() {
  const { projection, screenData } = useJarvis(); const state = record(projection); const presence = projectionRecord(state, 'presence'); const home = projectionRecord(state, 'home'); const context = screenData.context; const world = record(context.world_state || context.world)
  return <div className="screen"><SectionHeading eyebrow="LIVE PROJECTION" title="Current context" description="Fresh, bounded observations from perception, presence, workspace, and world-state services. Viewing this does not persist it to Memory." /><div className="screen-grid two"><FramePanel title="Desktop and presence" eyebrow="SOURCE-OWNED"><DetailList values={{ 'Active device': stringValue(presence.active_device_id, 'Not observed'), 'Active application': stringValue(presence.active_application || presence.active_app, 'Not observed'), 'Focused window': stringValue(presence.focused_window, 'Not observed'), Workspace: stringValue(presence.current_workspace, 'Not observed'), Session: stringValue(record(state.conversation).session_id, 'No active session'), Freshness: dateValue(context.generated_at || projection?.generated_at) }} /></FramePanel><FramePanel title="World state" eyebrow="BOUNDED FACTS">{Object.keys(world).length ? <DetailList values={Object.fromEntries(Object.entries(world).slice(0, 10).map(([key, value]) => [key, typeof value === 'object' ? 'Structured observation' : value]))} /> : <EmptyState title="No fresh world-state facts" detail="JARVIS will show observations when an approved provider reports them." />}</FramePanel></div><FramePanel title="Home context" eyebrow="CONNECTED SERVICES" status={home.available ? 'connected' : 'offline'}><DetailList values={{ Controller: home.available ? 'Live controller connected' : 'No live home controller connected', Entities: list(home.entities).length, Policy: 'No fake devices' }} /></FramePanel></div>
}

export function OperationsScreen() { const { projection } = useJarvis(); const state = record(projection); const operations = projectionRecord(state, 'operations'); const focus = projectionRecord(state, 'focus'); const modes = projectionList(state, 'automations'); const followups = projectionList(state, 'follow_ups'); return <div className="screen"><SectionHeading eyebrow="PERSONAL OPERATIONS" title="Operations" description="Modes, focus, briefings, automations, and follow-ups from the existing authorities." /><div className="screen-grid three"><FramePanel title="Current mode" status={record(operations.mode).mode || 'normal'}><DetailList values={{ Mode: stringValue(record(operations.mode).mode, 'normal'), 'Focus session': focus ? 'Active' : 'Inactive', 'Follow-ups': followups.length }} /><Link className="text-link" to="/notifications">Review attention queue →</Link></FramePanel><FramePanel title="Automations" status={modes.length ? 'active' : 'idle'}>{modes.length ? modes.slice(0, 6).map((item) => <div className="compact-row" key={stringValue(item.rule_id || item.id)}><strong>{stringValue(item.name || item.rule_id, 'Automation rule')}</strong><StatusBadge value={item.enabled ? 'enabled' : 'paused'} /></div>) : <EmptyState title="No automations configured" detail="Rules appear here only when the canonical operations service creates them." />}</FramePanel><FramePanel title="Follow-ups" status={followups.length ? 'pending' : 'clear'}>{followups.length ? followups.slice(0, 5).map((item) => <div className="compact-row" key={stringValue(item.follow_up_id || item.id)}><div><strong>{stringValue(item.subject || item.title, 'Follow-up')}</strong><span>{dateValue(item.due_at || item.created_at)}</span></div><StatusBadge value={item.status || 'active'} /></div>) : <EmptyState title="No active follow-ups" detail="Resolved items remain in the backend history." />}</FramePanel></div></div> }

export function ResearchScreen() { const { api, screenData, screenLoading, setScreenData, refreshProjection, setError } = useJarvis(); const [query, setQuery] = useState(''); const [starting, setStarting] = useState(false); const [evidence, setEvidence] = useState<JsonRecord[]>([])
  async function start(event: React.FormEvent) { event.preventDefault(); if (!query.trim()) return; setStarting(true); try { await api.post('/research/runs', { query: query.trim() }); setQuery(''); await Promise.all([refreshProjection(), load()]) } catch (error) { setError(error instanceof Error ? error.message : 'Research request failed.') } finally { setStarting(false) } }
  async function load() { const payload = await api.get<{ runs?: unknown[] }>('/research/runs'); setScreenData({ research: list(payload.runs) }) }
  async function showEvidence(item: JsonRecord) { try { const id = stringValue(item.run_id || item.id); const payload = await api.get<unknown>(`/research/runs/${encodeURIComponent(id)}/evidence`); setEvidence(list(evidenceFromPayload(payload))) } catch (error) { setError(error instanceof Error ? error.message : 'Evidence unavailable.') } }
  return <div className="screen"><SectionHeading eyebrow="EVIDENCE LEDGER" title="Research" description="Persisted research runs and evidence. Web access remains explicit when the provider is unavailable." /><Panel className="toolbar-panel"><form className="search-form" onSubmit={(event) => void start(event)}><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Start a local research request…" aria-label="Research request" /><Button variant="primary" type="submit" disabled={starting || !query.trim()}>{starting ? 'Starting…' : 'Start research'}</Button></form></Panel><div className="screen-grid two">{screenLoading ? <LoadingState /> : screenData.research.length ? screenData.research.map((item) => <ListCard key={stringValue(item.run_id || item.id)} title={stringValue(item.query, 'Research run')} status={item.status} meta={dateValue(item.created_at)}><DetailList values={{ Completed: dateValue(item.completed_at), Sources: item.source_count ?? item.evidence_count ?? 'Not reported', Error: stringValue(item.error_code, 'None') }} /><div className="card-actions inline"><Button onClick={() => void showEvidence(item)}>View evidence</Button>{['queued', 'running', 'started'].includes(stringValue(item.status)) && <Button variant="danger" onClick={() => void api.post(`/research/runs/${encodeURIComponent(stringValue(item.run_id || item.id))}/cancel`, {}).then(load).catch((error) => setError(error instanceof Error ? error.message : 'Research cancellation failed.'))}>Cancel</Button>}</div></ListCard>) : <Panel><EmptyState title="No research runs" detail="Research runs appear here when the existing ResearchService is used." /></Panel>}</div>{evidence.length > 0 && <Panel className="evidence-panel"><div className="panel-head"><h2>Evidence</h2><Button onClick={() => setEvidence([])}>Close</Button></div>{evidence.map((item, index) => <div className="evidence-row" key={stringValue(item.evidence_id || item.id, String(index))}><strong>{stringValue(item.title || item.source, 'Source')}</strong><p>{stringValue(item.excerpt || item.content, 'No excerpt')}</p><span className="muted small">{stringValue(item.url, 'Local evidence')}</span></div>)}</Panel>}</div>
}

export function SkillsScreen() { const { api, projection, refreshProjection, setError } = useJarvis(); const skills = projectionList(record(projection), 'skills'); async function toggle(item: JsonRecord) { const id = stringValue(item.skill_id || item.id); const enabled = Boolean(item.enabled ?? item.status === 'enabled'); try { await api.post(`/skills/${encodeURIComponent(id)}/${enabled ? 'disable' : 'enable'}`, {}); await refreshProjection() } catch (error) { setError(error instanceof Error ? error.message : 'Skill policy update failed.') } } return <div className="screen"><SectionHeading eyebrow="CAPABILITY REGISTRY" title="Skills" description="Installed skill metadata from the product-owned registry. Enablement and execution remain policy-controlled." /><div className="screen-grid three">{skills.length ? skills.map((item) => <ListCard key={stringValue(item.skill_id || item.id)} title={stringValue(item.name || item.skill_id, 'Skill')} status={item.enabled ? 'enabled' : item.status || 'disabled'} meta={stringValue(item.source, 'Product registry')}><p className="card-copy">{stringValue(item.description, 'No description')}</p><DetailList values={{ Version: item.version || item.current_version || 'Not reported', Risk: item.risk_level || 'Not reported', Capabilities: list(item.capabilities).length || 'Not reported', 'Last used': dateValue(item.last_used) }} /><div className="card-actions"><Button onClick={() => void toggle(item)}>{item.enabled ? 'Disable' : 'Enable'}</Button></div></ListCard>) : <Panel><EmptyState title="No skills installed" detail="The registry is the source of truth; no fixture skills are shown." /></Panel>}</div></div> }

export function DevicesScreen() { const { projection } = useJarvis(); const devices = projectionList(record(projection), 'devices'); return <div className="screen"><SectionHeading eyebrow="DEVICE FABRIC" title="Devices & home" description="Actual registered device and home-controller state. A device is never marked live without backend evidence." /><div className="screen-grid two">{devices.length ? devices.map((item) => <ListCard key={stringValue(item.device_id || item.id)} title={stringValue(item.name || item.device_id, 'Device')} status={item.status} meta={stringValue(item.role, 'Registered device')}><DetailList values={{ Device: stringValue(item.device_id || item.id), 'Last seen': dateValue(item.last_seen), Capabilities: list(item.capabilities).length ? `${list(item.capabilities).length} reported` : 'None reported', Health: stringValue(item.health, 'Not reported') }} /></ListCard>) : <Panel><EmptyState title="No registered devices" detail="Connect a device through the canonical device authority." /></Panel>}</div><Panel><EmptyState title="No live home controller connected" detail="Home integration will appear when configured; the UI does not fabricate device state." /></Panel></div> }

export function NotificationsScreen() {
  const { api, projection, refreshProjection, setError } = useJarvis()
  const notifications = projectionList(record(projection), 'notifications')
  const [filter, setFilter] = useState<NotificationFilter>('all')
  const visible = useMemo(() => filterNotifications(notifications, filter), [filter, notifications])
  async function dismiss(item: JsonRecord) {
    try { await api.post(`/notifications/${encodeURIComponent(stringValue(item.notification_id || item.id))}/dismiss`, {}); await refreshProjection() }
    catch (error) { setError(error instanceof Error ? error.message : 'Notification dismissal failed.') }
  }
  const filters: Array<[NotificationFilter, string]> = [['all', 'All'], ['unread', 'Unread'], ['important', 'Important'], ['proactive', 'Proactive'], ['system', 'System']]
  return <div className="screen"><SectionHeading eyebrow="OWNER ATTENTION" title="Notifications" description="Unread, proactive, and system notices from the existing notification service." /><div className="filter-tabs large">{filters.map(([value, label]) => <button className={filter === value ? 'selected' : ''} key={value} onClick={() => setFilter(value)}>{label}{value === 'all' && <span> {notifications.length}</span>}</button>)}</div><Panel>{visible.length ? <div className="notification-list">{visible.map((item) => <div className="notification-row" key={stringValue(item.notification_id || item.id)}><span className={`notification-marker ${tone(item.severity)}`} /><div><div className="card-heading"><strong>{stringValue(item.title, 'Notification')}</strong><StatusBadge value={item.severity || 'info'} /></div><p>{stringValue(item.message, '')}</p><span className="muted small">{dateValue(item.created_at)}</span></div>{!item.dismissed && <Button variant="quiet" onClick={() => void dismiss(item)}>Dismiss</Button>}</div>)}</div> : <EmptyState title="No notifications in this view" detail="JARVIS will surface important changes without turning local operation into noise." />}</Panel></div>
}

export function ApprovalsScreen() { const { api, projection, refreshProjection, setError } = useJarvis(); const approvals = projectionList(record(projection), 'approvals'); async function decision(item: JsonRecord, approved: boolean) { const runId = stringValue(item.run_id || item.pending_run_id, ''); if (!runId) return; try { await api.post(`/approvals/${encodeURIComponent(stringValue(item.approval_id || item.id))}`, { run_id: runId, approved }); await refreshProjection() } catch (error) { setError(error instanceof Error ? error.message : 'Approval decision failed.') } } return <div className="screen"><SectionHeading eyebrow="OWNER CONTROL" title="Approval center" description="Consequential actions remain backend-authoritative. Each decision is owner-scoped, CSRF-protected, and audited." /><div className="screen-grid two">{approvals.length ? approvals.map((item) => <ApprovalCard key={stringValue(item.approval_id || item.id)} approval={item} onDecision={decision} />) : <Panel><EmptyState title="No pending approvals" detail="JARVIS will show the exact action, target, reason, risk, and sanitized preview here." /></Panel>}</div></div> }

export function ActivityScreen() { const { projection } = useJarvis(); const timeline = projectionList(record(projection), 'timeline'); return <div className="screen"><SectionHeading eyebrow="AUDIT PROJECTION" title="Activity" description="A readable owner-facing timeline. Sensitive payloads are redacted before reaching this projection." /><FramePanel title="Runtime timeline" eyebrow={`${timeline.length} RECORDED EVENTS`}><ActivityList events={timeline} limit={100} /></FramePanel></div> }

export function EngineeringScreen() { const { projection } = useJarvis(); const items = projectionList(record(projection), 'worker_delegations').concat(projectionList(record(projection), 'engineering')); return <div className="screen"><SectionHeading eyebrow="DEVELOPER WORKERS" title="Engineering" description="Read-only worker and engineering-session state. Terminal streaming remains intentionally deferred." /><div className="screen-grid two">{items.length ? items.map((item, index) => <ListCard key={stringValue(item.session_id || item.worker_id, String(index))} title={stringValue(item.provider || item.worker_id, 'Engineering session')} status={item.status} meta={stringValue(item.session_id || item.worker_id)}><DetailList values={{ Session: stringValue(item.session_id, 'Not reported'), 'Last action': stringValue(item.last_action || item.action, 'Not reported'), Artifacts: item.artifact_count ?? 'Not reported' }} /></ListCard>) : <Panel><EmptyState title="No active engineering workers" detail="Worker state appears when the existing engineering service creates a session." /></Panel>}</div></div> }

export function BrowserScreen() { return <div className="screen"><SectionHeading eyebrow="SAFE CAPABILITY SURFACE" title="Browser" description="Browser work remains behind the existing browser authority, session, permission, and approval policy." /><Panel className="deferred-panel"><span className="deferred-icon">↗</span><h2>No live browser job</h2><StatusBadge value="unavailable" /><p>The product UI will display real browser capability results when a configured local controller reports them. It does not fabricate tabs, navigation, or web content.</p><Link className="button secondary" to="/approvals">Review approvals</Link></Panel></div> }

export function SettingsScreen() { const { projection, screenData } = useJarvis(); const health = screenData.health; const system = projectionRecord(record(projection), 'system'); const model = record(health.local_model || health.model); const voice = projectionRecord(record(projection), 'voice'); return <div className="screen"><SectionHeading eyebrow="CONFIGURATION" title="Settings & health" description="Operational truth, privacy controls, and safe product surfaces for the local runtime." /><div className="settings-grid"><FramePanel title="System health" status={health.state || system.runtime_state}><DetailList values={{ Core: health.state || system.runtime_state || 'Not reported', Database: health.database || 'Not reported', 'Local model': model.available || system.model_available ? 'Ready' : 'Unavailable', Provider: model.provider || system.model_provider || 'Not reported', Voice: voice.state || 'No active voice session', Venom: record(health.venom).status || 'Not connected' }} /></FramePanel><FramePanel title="Privacy center" eyebrow="LOCAL POLICY"><DetailList values={{ 'Local brain': 'YES', 'Raw audio stored': 'NO', 'Raw screenshots stored': 'NO', 'Core cloud dependency': 'NO', Memory: 'Inspectable / editable / deletable', Credentials: 'HttpOnly session boundary' }} /><div className="notice">Physical voice acceptance is intentionally deferred. Normal voice operational state remains visible when the backend reports it.</div></FramePanel><FramePanel title="Preferences" eyebrow="PRODUCT SURFACE"><div className="settings-list"><div>General <span>Read-only in this release; no editable preference control is exposed.</span></div><Link to="/devices">Devices <span>Registered device status</span></Link><Link to="/skills">Skills <span>Policy-controlled capabilities</span></Link><div>Advanced diagnostics <span>Available through the desktop repair surface; not a fabricated in-app route.</span></div></div></FramePanel><FramePanel title="Voice status" eyebrow="OPERATIONAL ONLY"><div className="voice-status"><JWaveform active={['listening', 'speaking'].includes(stringValue(voice.state))} /><DetailList values={{ State: statusText(voice.state || 'sleeping'), Microphone: stringValue(voice.microphone, 'Not reported'), Speaker: stringValue(voice.speaker, 'Not reported'), Wake: stringValue(voice.wake, 'Not reported'), STT: stringValue(voice.stt, 'Not reported'), TTS: stringValue(voice.tts, 'Not reported') }} /></div></FramePanel></div></div> }

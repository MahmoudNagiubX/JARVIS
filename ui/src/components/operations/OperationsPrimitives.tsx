import type { ReactNode } from 'react'
import type { JsonRecord } from '../../lib/format'
import { dateValue, list, stringValue, tone } from '../../lib/format'

/**
 * Adapted from donor 04_mission_control task-pipeline and conversation
 * presentation. These components intentionally accept JARVIS DTOs rather
 * than owning donor stores or mission state.
 */
export function ConversationRail({ conversations, selected, onSelect, onNew }: { conversations: JsonRecord[]; selected: string; onSelect: (id: string) => void; onNew: () => void }) {
  return <aside className="conversation-rail" data-testid="conversation-rail"><div className="rail-title"><div><span className="eyebrow">MISSION LOG</span><h2>Conversations</h2></div><button className="text-button" onClick={onNew}>New</button></div><div className="conversation-stack">{conversations.length ? conversations.map((item) => { const id = stringValue(item.id); return <button className={`conversation-item ${selected === id ? 'selected' : ''}`} key={id} onClick={() => onSelect(id)}><span className="conversation-signal" /><span><strong>{stringValue(item.title, 'Untitled conversation')}</strong><small>{dateValue(item.updated_at || item.last_message_at)}</small></span></button> }) : <div className="compact-empty">No saved conversations<br /><span>Your first message creates one.</span></div>}</div></aside>
}

export function RichMessage({ message, activity = [] }: { message: JsonRecord; activity?: JsonRecord[] }) {
  const isUser = message.role === 'user'
  return <article className={`rich-message ${isUser ? 'from-owner' : 'from-jarvis'}`}><div className="message-meta"><span>{isUser ? 'YOU' : 'JARVIS'}</span><time>{dateValue(message.created_at)}</time></div><p>{stringValue(message.content, '')}</p>{activity.length > 0 && <div className="message-tools">{activity.map((tool, index) => <div className="message-tool" key={stringValue(tool.tool_call_id || tool.name, String(index))}><i />{stringValue(tool.name || tool.tool, 'Tool activity')}<span className={tone(tool.status)}>{stringValue(tool.status, 'recorded')}</span></div>)}</div>}</article>
}

export function RunInbox({ runs }: { runs: JsonRecord[] }) {
  return <div className="run-inbox"><div className="run-inbox-title"><span className="eyebrow">BACKGROUND INBOX</span><span>{runs.length} tracked</span></div>{runs.length ? runs.slice(-4).reverse().map((run, index) => <div className="run-inbox-row" key={stringValue(run.run_id || run.mission_id, String(index))}><span className={`run-pip ${tone(run.state || run.status)}`} /><div><strong>{stringValue(run.title || run.name || run.run_id, 'Background run')}</strong><small>{stringValue(run.state || run.status, 'reported')}</small></div><time>{dateValue(run.updated_at || run.created_at)}</time></div>) : <div className="compact-empty">No background work is running.</div>}</div>
}

/** Adapted from donor 04 task-pipeline-widget and donor 06 Plan/ProgressTracker. */
export function MissionPipeline({ missions }: { missions: JsonRecord[] }) {
  const stages = [
    { key: 'planning', label: 'planning', statuses: ['draft', 'planned'] },
    { key: 'active', label: 'active', statuses: ['active', 'running'] },
    { key: 'review', label: 'review', statuses: ['waiting_approval', 'paused'] },
    { key: 'closed', label: 'closed', statuses: ['completed', 'failed', 'cancelled'] },
  ]
  return <div className="mission-pipeline" data-testid="mission-pipeline">{stages.map((stage) => { const items = missions.filter((mission) => stage.statuses.includes(stringValue(mission.status, 'draft'))); return <div className="pipeline-stage" key={stage.key}><div className="pipeline-stage-head"><span>{stage.label}</span><strong>{items.length}</strong></div>{items.slice(0, 4).map((mission) => <div className="pipeline-item" key={stringValue(mission.mission_id || mission.id)}><span className={`pipeline-dot ${tone(mission.status)}`} /><strong>{stringValue(mission.title || mission.request, 'Untitled mission')}</strong><small>{stringValue(mission.current_step, 'No active step')}</small></div>)}</div> })}</div>
}

export function PlanSurface({ title, steps }: { title: string; steps: Array<{ label: string; status?: unknown }> }) {
  return <div className="plan-surface"><div className="plan-title"><span className="eyebrow">EXECUTION PLAN</span><strong>{title}</strong></div>{steps.map((step, index) => <div className="plan-step" key={`${step.label}-${index}`}><span className={`plan-index ${tone(step.status)}`}>{index + 1}</span><span>{step.label}</span><b>{stringValue(step.status, 'pending').replace('_', ' ')}</b></div>)}</div>
}

export function ProgressSurface({ label, value, status }: { label: string; value?: unknown; status?: unknown }) {
  const numeric = typeof value === 'number' ? Math.min(Math.max(value, 0), 100) : null
  return <div className="progress-surface"><div><span>{label}</span><strong>{numeric === null ? stringValue(status, 'reported') : `${numeric}%`}</strong></div>{numeric !== null && <div className="progress-track"><i style={{ width: `${numeric}%` }} /></div>}</div>
}

export function FieldTable({ rows }: { rows: Array<[string, ReactNode]> }) {
  return <div className="field-table">{rows.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
}

export function ProjectionSummary({ items }: { items: Array<{ label: string; value: ReactNode; detail?: string }> }) {
  return <div className="projection-summary">{items.map((item) => <div key={item.label}><span>{item.label}</span><strong>{item.value}</strong>{item.detail && <small>{item.detail}</small>}</div>)}</div>
}

export function countReportedCapabilities(item: JsonRecord): string {
  const count = list(item.capabilities).length
  return count ? `${count} reported` : 'None reported'
}

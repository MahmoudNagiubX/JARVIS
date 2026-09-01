import { useState, type ReactNode } from 'react'
import type { JsonRecord } from '../../lib/format'
import { dateValue, list, stringValue, tone } from '../../lib/format'

/**
 * Adapted from donor 04_mission_control (task-pipeline, message-bubble, chat-utils)
 * and donor 06_tool_ui (Plan, ProgressTracker, DecisionActions).
 * All presentation is product-owned and receives canonical JARVIS projection state.
 */
export function ConversationRail({
  conversations,
  selected,
  onSelect,
  onNew,
}: {
  conversations: JsonRecord[]
  selected: string
  onSelect: (id: string) => void
  onNew: () => void
}) {
  return (
    <aside className="conversation-rail" data-testid="conversation-rail">
      <div className="rail-title">
        <div>
          <span className="eyebrow">MISSION LOG</span>
          <h2>Conversations</h2>
        </div>
        <button className="text-button" onClick={onNew}>+ New</button>
      </div>
      <div className="conversation-stack">
        {conversations.length ? (
          conversations.map((item) => {
            const id = stringValue(item.id)
            const isSelected = selected === id
            return (
              <button
                className={`conversation-item ${isSelected ? 'selected' : ''}`}
                key={id}
                onClick={() => onSelect(id)}
              >
                <span className={`conversation-signal ${isSelected ? 'live' : ''}`} />
                <span className="conversation-info">
                  <strong>{stringValue(item.title, 'Untitled conversation')}</strong>
                  <small>{dateValue(item.updated_at || item.last_message_at)}</small>
                </span>
              </button>
            )
          })
        ) : (
          <div className="compact-empty">
            No saved conversations<br />
            <span>Your first message creates one.</span>
          </div>
        )}
      </div>
    </aside>
  )
}

export function RichMessage({
  message,
  activity = [],
}: {
  message: JsonRecord
  activity?: JsonRecord[]
}) {
  const isUser = message.role === 'user'
  const content = stringValue(message.content, '')
  const [expandedTools, setExpandedTools] = useState<Record<string, boolean>>({})

  const toggleTool = (id: string) => {
    setExpandedTools((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  // Parse basic code blocks for holographic code presentation
  const renderFormattedContent = (text: string) => {
    if (!text.includes('```')) {
      return <p className="message-text">{text}</p>
    }
    const parts = text.split(/(```[\s\S]*?```)/g)
    return parts.map((part, i) => {
      if (part.startsWith('```') && part.endsWith('```')) {
        const code = part.slice(3, -3).replace(/^\w+\n/, '')
        return (
          <pre key={i} className="message-code-block">
            <code>{code}</code>
          </pre>
        )
      }
      return part ? <p key={i} className="message-text">{part}</p> : null
    })
  }

  return (
    <article className={`rich-message ${isUser ? 'from-owner' : 'from-jarvis'}`}>
      <div className="message-meta">
        <span className="message-role-tag">
          <i className="message-role-pip" />
          {isUser ? 'YOU' : 'JARVIS'}
        </span>
        <time>{dateValue(message.created_at)}</time>
      </div>

      <div className="message-body">
        {renderFormattedContent(content)}
      </div>

      {activity.length > 0 && (
        <div className="message-tools" data-testid="message-tools">
          <div className="message-tools-heading">
            <span className="eyebrow">TOOL ACTIVITY</span>
            <small>{activity.length} action{activity.length === 1 ? '' : 's'}</small>
          </div>
          {activity.map((tool, index) => {
            const toolId = stringValue(tool.tool_call_id || tool.name, String(index))
            const toolName = stringValue(tool.name || tool.tool, 'Tool activity')
            const toolStatus = stringValue(tool.status, 'recorded')
            const isExpanded = Boolean(expandedTools[toolId])
            const toolArgs = tool.args || tool.arguments
            const toolResult = tool.result || tool.output

            return (
              <div className="message-tool" key={toolId}>
                <button
                  type="button"
                  className="message-tool-header"
                  onClick={() => toggleTool(toolId)}
                  aria-expanded={isExpanded}
                  aria-label={`${toolName} details`}
                >
                  <i className={`tool-status-dot ${tone(toolStatus)}`} />
                  <span className="tool-name">{toolName}</span>
                  <span className={`tool-badge ${tone(toolStatus)}`}>{toolStatus}</span>
                  {Boolean(toolArgs || toolResult) && (
                    <span className={`tool-expand-arrow ${isExpanded ? 'open' : ''}`}>›</span>
                  )}
                </button>
                {isExpanded && (
                  <div className="message-tool-detail">
                    {Boolean(toolArgs) && (
                      <div className="tool-meta-block">
                        <span className="tool-meta-label">INPUT</span>
                        <pre>{typeof toolArgs === 'object' ? JSON.stringify(toolArgs, null, 2) : String(toolArgs)}</pre>
                      </div>
                    )}
                    {Boolean(toolResult) && (
                      <div className="tool-meta-block">
                        <span className="tool-meta-label">OUTPUT</span>
                        <pre>{typeof toolResult === 'object' ? JSON.stringify(toolResult, null, 2) : String(toolResult)}</pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </article>
  )
}

export function RunInbox({ runs }: { runs: JsonRecord[] }) {
  return (
    <div className="run-inbox">
      <div className="run-inbox-title">
        <span className="eyebrow">BACKGROUND INBOX</span>
        <span>{runs.length} tracked</span>
      </div>
      {runs.length ? (
        runs.slice(-4).reverse().map((run, index) => (
          <div className="run-inbox-row" key={stringValue(run.run_id || run.mission_id, String(index))}>
            <span className={`run-pip ${tone(run.state || run.status)}`} />
            <div className="run-info">
              <strong>{stringValue(run.title || run.name || run.run_id, 'Background run')}</strong>
              <small>{stringValue(run.state || run.status, 'reported')}</small>
            </div>
            <time>{dateValue(run.updated_at || run.created_at)}</time>
          </div>
        ))
      ) : (
        <div className="compact-empty">No background work is running.</div>
      )}
    </div>
  )
}

/**
 * Adapted from donor 04 task-pipeline-widget and donor 06 Plan/ProgressTracker.
 * Renders four tactical stages of execution without storing local runtime state.
 */
export function MissionPipeline({ missions }: { missions: JsonRecord[] }) {
  const stages = [
    { key: 'planning', label: 'planning', statuses: ['draft', 'planned'] },
    { key: 'active', label: 'active', statuses: ['active', 'running'] },
    { key: 'review', label: 'review', statuses: ['waiting_approval', 'paused'] },
    { key: 'closed', label: 'closed', statuses: ['completed', 'failed', 'cancelled'] },
  ]

  return (
    <div className="mission-pipeline" data-testid="mission-pipeline">
      {stages.map((stage) => {
        const items = missions.filter((mission) =>
          stage.statuses.includes(stringValue(mission.status, 'draft'))
        )
        return (
          <div className="pipeline-stage" key={stage.key}>
            <div className="pipeline-stage-head">
              <span>{stage.label}</span>
              <strong>{items.length}</strong>
            </div>
            <div className="pipeline-stage-items">
              {items.slice(0, 4).map((mission) => (
                <div className="pipeline-item" key={stringValue(mission.mission_id || mission.id)}>
                  <span className={`pipeline-dot ${tone(mission.status)}`} />
                  <div className="pipeline-item-content">
                    <strong>{stringValue(mission.title || mission.request, 'Untitled mission')}</strong>
                    <small>{stringValue(mission.current_step, 'No active step')}</small>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/**
 * PlanSurface adapts step progress tracking and connector lines from Donor 06 Plan/ProgressTracker.
 */
export function PlanSurface({
  title,
  steps,
}: {
  title: string
  steps: Array<{ label: string; status?: unknown; description?: string }>
}) {
  return (
    <div className="plan-surface">
      <div className="plan-title">
        <span className="eyebrow">EXECUTION PLAN</span>
        <strong>{title}</strong>
      </div>
      <div className="plan-step-list">
        {steps.map((step, index) => {
          const stepStatus = stringValue(step.status, 'pending')
          const isDone = ['completed', 'done', 'success'].includes(stepStatus)
          const isActive = ['active', 'running', 'in_progress'].includes(stepStatus)
          return (
            <div className={`plan-step ${isActive ? 'active' : ''}`} key={`${step.label}-${index}`}>
              <div className="plan-step-indicator">
                <span className={`plan-index ${tone(step.status)}`}>
                  {isDone ? '✓' : index + 1}
                </span>
                {index < steps.length - 1 && <span className="plan-connector" />}
              </div>
              <div className="plan-step-content">
                <span className="plan-step-label">{step.label}</span>
                {step.description && <small className="plan-step-desc">{step.description}</small>}
              </div>
              <b className={`plan-step-badge ${tone(step.status)}`}>
                {stepStatus.replace('_', ' ')}
              </b>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/**
 * ProgressSurface adapts Donor 03 JProgress tick gauge and smooth SVG track.
 */
export function ProgressSurface({
  label,
  value,
  status,
  variant = 'bar',
}: {
  label: string
  value?: unknown
  status?: unknown
  variant?: 'bar' | 'ticks'
}) {
  const numeric = typeof value === 'number' ? Math.min(Math.max(value, 0), 100) : null
  const totalTicks = 16
  const activeTicks = numeric !== null ? Math.round((numeric / 100) * totalTicks) : 0

  return (
    <div className="progress-surface">
      <div className="progress-head">
        <span className="progress-label">{label}</span>
        <strong className="progress-value">
          {numeric === null ? stringValue(status, 'reported') : `${numeric}%`}
        </strong>
      </div>

      {numeric !== null && (
        variant === 'ticks' ? (
          <div className="progress-tick-row">
            {Array.from({ length: totalTicks }, (_, i) => (
              <span
                key={i}
                className={`progress-tick ${i < activeTicks ? 'active' : 'inactive'}`}
              />
            ))}
          </div>
        ) : (
          <div className="progress-track">
            <i style={{ width: `${numeric}%` }} />
          </div>
        )
      )}
    </div>
  )
}

/**
 * ConfidenceMeter adapts Donor 08 drawMiniBar and Donor 03 JGaugeChart.
 * Renders a segmented confidence rating from 0% to 100%.
 */
export function ConfidenceMeter({ value }: { value?: unknown }) {
  const numeric = typeof value === 'number'
    ? Math.min(Math.max(value <= 1 ? value * 100 : value, 0), 100)
    : null

  if (numeric === null) {
    return <span className="confidence-text muted">Not reported</span>
  }

  const rounded = Math.round(numeric)
  const segments = 5
  const activeSegments = Math.round((numeric / 100) * segments)
  const toneClass = numeric >= 75 ? 'good' : numeric >= 40 ? 'warn' : 'bad'

  return (
    <div className="confidence-meter" data-testid="confidence-meter" aria-label={`Confidence: ${rounded}%`}>
      <div className="confidence-segments">
        {Array.from({ length: segments }, (_, i) => (
          <span
            key={i}
            className={`confidence-segment ${i < activeSegments ? `active ${toneClass}` : 'inactive'}`}
          />
        ))}
      </div>
      <strong className={`confidence-val ${toneClass}`}>{rounded}%</strong>
    </div>
  )
}

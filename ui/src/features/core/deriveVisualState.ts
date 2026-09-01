import type { ExperienceState } from '../../lib/events'
import { list, record, stringValue } from '../../lib/format'

export type JarvisVisualState =
  | 'idle'
  | 'ready'
  | 'thinking'
  | 'tool'
  | 'researching'
  | 'waiting_approval'
  | 'speaking'
  | 'degraded'
  | 'offline'
  | 'error'

function normalized(value: unknown): string {
  return stringValue(value, '').toLowerCase().replaceAll('-', '_').replaceAll(' ', '_')
}

function hasState(items: unknown[], states: Set<string>): boolean {
  return items.some((item) => states.has(normalized(record(item).state || record(item).status)))
}

/**
 * Presentation-only state adapter. It intentionally consumes the existing
 * projection and never stores or invents a second runtime state machine.
 */
export function deriveVisualState(projection: ExperienceState | null): JarvisVisualState {
  if (!projection) return 'offline'

  const system = record(projection.system)
  const voice = record(projection.voice)
  const operations = record(projection.operations)
  const runtime = normalized(system.runtime_state || projection.state)
  const voiceState = normalized(voice.state)
  const operationState = normalized(operations.state || operations.status)
  const approvals = list(projection.approvals)
  const runs = [
    ...list(projection.runs),
    ...list(projection.active_runs),
    ...list(projection.tool_activity),
  ]

  if (['error', 'failed', 'unhealthy', 'critical_error'].includes(runtime)) return 'error'
  if (approvals.some((item) => ['pending', 'waiting', 'waiting_approval', 'approval_required', 'paused'].includes(normalized(record(item).status || record(item).state)))) return 'waiting_approval'
  if (['speaking', 'responding', 'tts', 'voice_output'].includes(voiceState)) return 'speaking'
  if (['running', 'started', 'researching', 'research'].includes(normalized(record(projection.research).state)) || hasState(list(projection.research), new Set(['running', 'started', 'researching']))) return 'researching'
  if (['tool', 'tool_running', 'executing', 'action_running'].includes(operationState) || hasState(runs, new Set(['tool', 'tool_running', 'executing', 'running']))) return 'tool'
  if (['thinking', 'processing', 'generating', 'queued', 'starting'].includes(runtime) || ['listening', 'thinking', 'processing'].includes(voiceState)) return 'thinking'
  if (system.offline === true) return 'offline'
  if (['degraded', 'unavailable', 'reconnecting'].includes(runtime)) return 'degraded'
  if (['ready', 'online', 'idle', 'created'].includes(runtime)) return runtime === 'idle' ? 'idle' : 'ready'
  return 'idle'
}

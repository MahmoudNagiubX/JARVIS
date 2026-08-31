export interface ExperienceState {
  system: Record<string, unknown>
  approvals: unknown[]
  missions: unknown[]
  notifications: unknown[]
  devices: unknown[]
  [key: string]: unknown
}

export interface NormalizedSnapshot {
  kind: 'snapshot'
  data: ExperienceState
}

export interface NormalizedEvent {
  kind: 'event'
  data: Record<string, unknown>
}

export type NormalizedExperienceMessage = NormalizedSnapshot | NormalizedEvent

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isProjection(value: unknown): value is ExperienceState {
  return isRecord(value) && isRecord(value.system) && Array.isArray(value.approvals) && Array.isArray(value.missions)
}

export function normalizeExperienceEvent(payload: unknown): NormalizedExperienceMessage | null {
  if (!isRecord(payload) || typeof payload.type !== 'string') return null
  if (payload.type === 'state' && isProjection(payload.data)) return { kind: 'snapshot', data: payload.data }
  if (payload.type === 'event' && isRecord(payload.data)) return { kind: 'event', data: payload.data }
  return null
}

export function reconcileProjection(current: ExperienceState | null, message: NormalizedExperienceMessage): ExperienceState | null {
  return message.kind === 'snapshot' ? message.data : current
}

export function eventLabel(event: Record<string, unknown>): string {
  const raw = String(event.event_type || event.type || 'runtime event')
  return raw.replaceAll('_', ' ').replaceAll('.', ' ')
}

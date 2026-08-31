export type JsonRecord = Record<string, unknown>

export function record(value: unknown): JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as JsonRecord : {}
}

export function list(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.filter((item): item is JsonRecord => typeof item === 'object' && item !== null && !Array.isArray(item)) : []
}

export function stringValue(value: unknown, fallback = 'Not reported'): string {
  const text = String(value ?? '').trim()
  return text || fallback
}

export function title(value: unknown, fallback = 'Unknown'): string {
  return stringValue(value, fallback).replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase())
}

export function dateValue(value: unknown): string {
  if (!value) return 'No timestamp'
  const date = new Date(String(value))
  return Number.isNaN(date.valueOf()) ? stringValue(value) : date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

export function shortDate(value: unknown): string {
  if (!value) return 'No timestamp'
  const date = new Date(String(value))
  return Number.isNaN(date.valueOf()) ? stringValue(value) : date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export function tone(value: unknown): 'good' | 'warn' | 'bad' | '' {
  const lowered = stringValue(value, '').toLowerCase()
  if (['ready', 'idle', 'completed', 'succeeded', 'online', 'available', 'connected', 'pass', 'healthy', 'enabled'].includes(lowered)) return 'good'
  if (['degraded', 'paused', 'pending', 'waiting', 'approval_required', 'offline', 'unavailable', 'unknown', 'partial', 'starting'].includes(lowered)) return 'warn'
  if (['error', 'failed', 'cancelled', 'revoked', 'unhealthy', 'denied'].includes(lowered)) return 'bad'
  return ''
}

export function statusText(value: unknown): string {
  return title(value, 'Unknown')
}

export function jsonText(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (value === null || value === undefined) return 'None'
  if (Array.isArray(value)) return `${value.length} item${value.length === 1 ? '' : 's'}`
  if (typeof value === 'object') return `${Object.keys(value).length} field${Object.keys(value).length === 1 ? '' : 's'}`
  return 'Not available'
}

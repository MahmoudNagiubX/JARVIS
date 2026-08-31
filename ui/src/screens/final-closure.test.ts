import { describe, expect, it } from 'vitest'
import { evidenceFromPayload, filterNotifications, isApprovalActionable, sessionRefreshDelay } from './Screens'
import type { JsonRecord } from '../lib/format'

describe('Phase 14 final closure contracts', () => {
  it('unwraps the canonical research evidence envelope without dropping evidence', () => {
    const payload = { evidence: [{ evidence_id: 'evidence-1', excerpt: 'local proof' }] }
    expect(evidenceFromPayload(payload)).toEqual(payload.evidence)
  })

  it('filters notifications from canonical DTO fields', () => {
    const notifications: JsonRecord[] = [
      { notification_id: 'unread', source: 'runtime', severity: 'info', dismissed: false },
      { notification_id: 'important', source: 'runtime', severity: 'critical', dismissed: false },
      { notification_id: 'proactive', source: 'proactive', severity: 'info', dismissed: false },
      { notification_id: 'system', source: 'system', severity: 'info', dismissed: true },
    ]
    expect(filterNotifications(notifications, 'unread')).toHaveLength(3)
    expect(filterNotifications(notifications, 'important').map((item) => item.notification_id)).toEqual(['important'])
    expect(filterNotifications(notifications, 'proactive').map((item) => item.notification_id)).toEqual(['proactive'])
    expect(filterNotifications(notifications, 'system').map((item) => item.notification_id)).toEqual(['system'])
  })

  it('refreshes before expiry with a bounded delay and keeps approval actions actionable only with a run id', () => {
    expect(sessionRefreshDelay('2026-08-31T12:15:00.000Z', new Date('2026-08-31T12:00:00.000Z'))).toBe(14 * 60 * 1000)
    expect(sessionRefreshDelay(undefined, new Date('2026-08-31T12:00:00.000Z'))).toBeNull()
    expect(isApprovalActionable({ status: 'pending', run_id: 'run-1' })).toBe(true)
    expect(isApprovalActionable({ status: 'pending' })).toBe(false)
    expect(isApprovalActionable({ status: 'approved', run_id: 'run-1' })).toBe(false)
  })
})

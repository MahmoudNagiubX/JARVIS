import { describe, expect, it } from 'vitest'
import { NAV_GROUPS, PRIMARY_NAV_GROUPS, routeForLabel, ROUTES } from './routes'

describe('Command Center routes', () => {
  it('keeps all daily product screens under the single app entry', () => {
    expect(ROUTES).toEqual(expect.arrayContaining(['/','/chat','/missions','/memory','/context','/operations','/research','/engineering','/browser','/skills','/devices','/notifications','/approvals','/activity','/settings']))
    expect(NAV_GROUPS.flatMap((group) => group.items).length).toBeGreaterThan(10)
  })

  it('maps command palette labels to navigation routes without executing actions', () => {
    expect(routeForLabel('Current context')).toBe('/context')
    expect(routeForLabel('Settings')).toBe('/settings')
  })

  it('keeps the approved five-area information architecture explicit', () => {
    expect(PRIMARY_NAV_GROUPS[0].items.map((item) => item.label)).toEqual([
      'Command', 'Converse', 'Work', 'Memory', 'Automations',
    ])
    expect(PRIMARY_NAV_GROUPS[1].items.map((item) => item.label)).toEqual(['Approvals', 'System'])
    expect(ROUTES).toEqual(expect.arrayContaining(['/work', '/automations', '/system']))
  })
})

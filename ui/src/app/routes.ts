export interface NavItem {
  label: string
  path: string
  glyph: string
  description?: string
}

export interface NavGroup {
  label: string
  items: NavItem[]
}

/** The product information architecture. Compatibility surfaces remain below. */
export const PRIMARY_NAV_GROUPS: NavGroup[] = [
  {
    label: 'Primary',
    items: [
      { label: 'Command', path: '/', glyph: 'C', description: 'Live owner command center' },
      { label: 'Converse', path: '/chat', glyph: '↔', description: 'Talk with JARVIS' },
      { label: 'Work', path: '/work', glyph: 'W', description: 'Missions, research, and projects' },
      { label: 'Memory', path: '/memory', glyph: 'M', description: 'Inspectable retained context' },
      { label: 'Automations', path: '/automations', glyph: 'A', description: 'Rules, follow-ups, and routines' },
    ],
  },
  {
    label: 'Utilities',
    items: [
      { label: 'Approvals', path: '/approvals', glyph: '!', description: 'Owner checkpoints' },
      { label: 'System', path: '/system', glyph: 'S', description: 'Health, devices, and settings' },
    ],
  },
]

/** Existing routes stay reachable while the primary shell stays calm. */
export const COMPATIBILITY_NAV_GROUP: NavGroup = {
  label: 'More surfaces',
  items: [
    { label: 'Missions', path: '/missions', glyph: 'W', description: 'Mission detail' },
    { label: 'Current context', path: '/context', glyph: 'C', description: 'Desktop and world context' },
    { label: 'Operations', path: '/operations', glyph: 'O', description: 'Mode and focus detail' },
    { label: 'Research', path: '/research', glyph: 'R', description: 'Evidence-led research' },
    { label: 'Engineering', path: '/engineering', glyph: 'E', description: 'Worker sessions' },
    { label: 'Browser', path: '/browser', glyph: 'B', description: 'Browser authority' },
    { label: 'Skills', path: '/skills', glyph: 'K', description: 'Local skills' },
    { label: 'Devices', path: '/devices', glyph: 'D', description: 'Connected devices' },
    { label: 'Notifications', path: '/notifications', glyph: 'N', description: 'Attention queue' },
    { label: 'Activity', path: '/activity', glyph: 'T', description: 'Runtime timeline' },
    { label: 'Settings', path: '/settings', glyph: 'G', description: 'Compatibility settings route' },
  ],
}

export const NAV_GROUPS: NavGroup[] = [...PRIMARY_NAV_GROUPS, COMPATIBILITY_NAV_GROUP]
export const ROUTES = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.path))

export function routeForLabel(label: string): string {
  return NAV_GROUPS.flatMap((group) => group.items).find((item) => item.label.toLowerCase() === label.toLowerCase())?.path || '/'
}

export function labelForPath(path: string): string {
  return NAV_GROUPS.flatMap((group) => group.items).find((item) => item.path === path)?.label || 'Command'
}

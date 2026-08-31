export interface NavItem {
  label: string
  path: string
  glyph: string
}

export interface NavGroup {
  label: string
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  { label: 'Workspace', items: [
    { label: 'Home', path: '/', glyph: '◈' },
    { label: 'Chat', path: '/chat', glyph: '◌' },
    { label: 'Missions', path: '/missions', glyph: '≋' },
    { label: 'Memory', path: '/memory', glyph: '▣' },
    { label: 'Current context', path: '/context', glyph: '⌖' },
  ] },
  { label: 'Capabilities', items: [
    { label: 'Operations', path: '/operations', glyph: '◫' },
    { label: 'Research', path: '/research', glyph: '⌁' },
    { label: 'Engineering', path: '/engineering', glyph: '⌘' },
    { label: 'Browser', path: '/browser', glyph: '↗' },
    { label: 'Skills', path: '/skills', glyph: '✦' },
    { label: 'Devices', path: '/devices', glyph: '⌁' },
    { label: 'Notifications', path: '/notifications', glyph: '!' },
  ] },
  { label: 'Control', items: [
    { label: 'Approvals', path: '/approvals', glyph: '✓' },
    { label: 'Activity', path: '/activity', glyph: '≡' },
    { label: 'Settings', path: '/settings', glyph: '⚙' },
  ] },
]

export const ROUTES = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.path))

export function routeForLabel(label: string): string {
  return NAV_GROUPS.flatMap((group) => group.items).find((item) => item.label.toLowerCase() === label.toLowerCase())?.path || '/'
}

export function labelForPath(path: string): string {
  return NAV_GROUPS.flatMap((group) => group.items).find((item) => item.path === path)?.label || 'Home'
}

import type { JarvisVisualState } from '../../features/core/deriveVisualState'
import type { ReactNode } from 'react'
import { HoloRing } from './HoloRing'

export function HolographicCore({ state = 'ready', label = 'JARVIS CORE', size = 132, children }: { state?: JarvisVisualState; label?: string; size?: number; children?: ReactNode }) {
  return <div className="holographic-core-v3" data-testid="holographic-core" data-state={state}><HoloRing state={state} label={label} size={size} />{children && <div className="holographic-core-content">{children}</div>}</div>
}

import type { JarvisVisualState } from '../../features/core/deriveVisualState'
import type { ReactNode } from 'react'
import { HoloRing } from './HoloRing'

export interface HolographicCoreProps {
  state?: JarvisVisualState
  label?: string
  size?: number
  concept?: 'halo' | 'orb' | 'traces'
  children?: ReactNode
}

export function HolographicCore({
  state = 'ready',
  label = 'JARVIS CORE',
  size = 132,
  concept = 'halo',
  children,
}: HolographicCoreProps) {
  return (
    <div
      className={`holographic-core-v3 holographic-core-${concept}`}
      data-testid="holographic-core"
      data-state={state}
      data-concept={concept}
    >
      <HoloRing state={state} label={label} size={size} concept={concept} />
      {children && <div className="holographic-core-content">{children}</div>}
    </div>
  )
}

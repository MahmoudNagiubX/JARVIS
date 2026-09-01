import type { ReactNode } from 'react'
import { HolographicCore as HolographicCoreV3 } from '../holographic/HolographicCore'

/** Compatibility adapter for the V2 import path; the V3 ring owns the visual core. */
export function HolographicCore({ children, active = false }: { children: ReactNode; active?: boolean }) {
  return <div className={`holographic-core ${active ? 'is-active' : ''}`}><HolographicCoreV3 state={active ? 'ready' : 'idle'}>{children}</HolographicCoreV3></div>
}

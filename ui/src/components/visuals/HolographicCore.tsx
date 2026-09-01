import type { ReactNode } from 'react'

/**
 * Lightweight SVG adaptation of donor 09_holographic_3d depth rings and
 * pulse language. It has no synthetic graph, face identity, camera input, or
 * permanent WebGL loop.
 */
export function HolographicCore({ children, active = false }: { children: ReactNode; active?: boolean }) {
  return <div className={`holographic-core ${active ? 'is-active' : ''}`}><span className="holo-ring ring-a" aria-hidden="true" /><span className="holo-ring ring-b" aria-hidden="true" /><span className="holo-ring ring-c" aria-hidden="true" /><span className="holo-grid" aria-hidden="true" /><div className="holo-core-label">{children}</div></div>
}

import type { ReactNode } from 'react'

export function ScanPlane() {
  return <span className="scan-plane" aria-hidden="true" />
}

export function DataArc({ label, value }: { label: string; value: string | number }) {
  return <div className="data-arc"><span>{label}</span><strong>{value}</strong></div>
}

export function DepthGrid() {
  return <span className="depth-grid" aria-hidden="true" />
}

export function HoloLabel({ children }: { children: ReactNode }) {
  return <span className="holo-label">{children}</span>
}

export function HoloPanel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`holo-panel ${className}`.trim()}>{children}</section>
}

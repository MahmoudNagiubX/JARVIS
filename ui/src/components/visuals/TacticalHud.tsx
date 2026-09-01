import type { ReactNode } from 'react'
import { CompassStrip } from '../tactical/CompassStrip'
import { RadarSweep } from '../tactical/RadarSweep'

/**
 * Lightweight SVG adaptation of donor 08_tactical_hud gauge, compass, and
 * radar composition. Fictional targeting semantics and continuous WebGL are
 * deliberately excluded; labels are supplied by real JARVIS projections.
 */
export function ContextCompass({ label = 'LOCAL CONTEXT', value = 'UNOBSERVED' }: { label?: string; value?: ReactNode }) {
  return <div className="context-compass"><CompassStrip label={label} value={String(value)} /></div>
}

export function TacticalRadar({ points = 0, label = 'DEVICE RADAR' }: { points?: number; label?: string }) {
  return <div className="tactical-radar"><RadarSweep points={points} label={label} testId="tactical-radar" /></div>
}

export function SystemGauge({ label, value, detail }: { label: string; value: number; detail?: string }) {
  const bounded = Math.min(Math.max(value, 0), 100)
  return <div className="system-gauge"><div className="gauge-head"><span>{label}</span><strong>{bounded}%</strong></div><div className="gauge-track"><i style={{ width: `${bounded}%` }} /></div>{detail && <small>{detail}</small>}</div>
}

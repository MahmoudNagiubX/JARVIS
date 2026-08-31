import type { ReactNode } from 'react'

/** Adapted from donor 03 JHudFrame (MIT); presentation only. */
export function JHudFrame({ children, label = 'JARVIS · SYSTEM', live = false }: { children: ReactNode; label?: string; live?: boolean }) {
  return <div className="j-hud-frame">
    <span className="hud-corner top-left" aria-hidden="true" /><span className="hud-corner top-right" aria-hidden="true" />
    <span className="hud-corner bottom-left" aria-hidden="true" /><span className="hud-corner bottom-right" aria-hidden="true" />
    <div className="hud-bar"><span className="mono-label">{label}</span><span className="hud-bar-line" />{live && <span className="live-label"><i /> LIVE</span>}</div>
    <div className="j-hud-content">{children}</div>
  </div>
}

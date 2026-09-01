import type { ReactNode } from 'react'
import { JWaveform } from '../hud/JWaveform'
import { HolographicCore } from '../holographic/HolographicCore'
import { DataArc, DepthGrid, HoloLabel, ScanPlane } from '../holographic/Primitives'
import { PulseNetwork, type PulseNetworkNode } from '../holographic/PulseNetwork'
import { RadarSweep } from '../tactical/RadarSweep'
import { CompassStrip } from '../tactical/CompassStrip'
import { AmbientEnergy } from './AmbientEnergy'
import { CinematicBoot } from './CinematicBoot'
import type { JarvisVisualState } from '../../features/core/deriveVisualState'

export interface CinematicHeroProps {
  wallpaper: string
  state: JarvisVisualState
  description?: string
  focusedWindow: ReactNode
  application: ReactNode
  missionCount: number
  attentionCount: number
  voiceState: string
  deviceCount?: number
}

function heroStateBadge(state: JarvisVisualState): string {
  switch (state) {
    case 'ready':
      return 'READY'
    case 'offline':
      return 'LOCAL ONLY'
    case 'waiting_approval':
      return 'ATTENTION'
    case 'thinking':
    case 'tool':
    case 'researching':
      return 'WORKING'
    case 'speaking':
      return 'SPEAKING'
    case 'degraded':
    case 'error':
      return 'NEEDS ATTENTION'
    case 'idle':
    default:
      return 'IDLE'
  }
}

/**
 * CinematicHero renders the flagship owner wallpaper hero scene with
 * multi-layered HUD geometry, unobtrusive state-reactive core halo,
 * floating telemetry readouts, and primary JARVIS identity.
 */
export function CinematicHero({
  wallpaper,
  state,
  description,
  focusedWindow,
  application,
  missionCount,
  attentionCount,
  voiceState,
  deviceCount = 0,
}: CinematicHeroProps) {
  const speaking = ['listening', 'speaking', 'responding'].includes(voiceState.toLowerCase())
  const networkNodes: PulseNetworkNode[] = [
    { label: 'CORE', state },
    { label: 'VOICE', state: speaking ? 'speaking' : 'idle' },
    { label: 'MISSION', state: missionCount ? 'tool' : 'idle' },
  ]

  return (
    <section
      className={`cinematic-hero visual-state-${state}`}
      data-testid="cinematic-hero"
      data-visual-state={state}
      aria-label="JARVIS cinematic command scene"
    >
      {/* Background artwork & cinematic depth layers */}
      <div
        className="hero-art"
        data-testid="hero-art"
        style={{ backgroundImage: `url(${wallpaper})` }}
      />
      <div className="hero-art-shade" />
      <DepthGrid />
      <ScanPlane />
      <CinematicBoot state={state} />

      {/* Main HUD Scene */}
      <div className="hero-scene">
        {/* Left column: Primary JARVIS identity, state, and key arcs */}
        <div className="hero-copy">
          <HoloLabel>J.A.R.V.I.S. // OPERATIONS</HoloLabel>
          <div className="hero-state-line">
            <span className="hero-state" data-testid="hero-state">
              {state.replaceAll('_', ' ').toUpperCase()}
            </span>
            <span className="hero-scene-badge" data-testid="hero-status-badge">
              {heroStateBadge(state)}
            </span>
          </div>

          <h2 className="hero-identity">JARVIS</h2>
          {description && <p className="hero-lede">{description}</p>}

          <div className="hero-signal-row">
            <DataArc label="CORE" value={state.replaceAll('_', ' ').toUpperCase()} />
            <DataArc label="VOICE" value={speaking ? 'ACTIVE' : voiceState.toUpperCase() || 'IDLE'} />
            <DataArc label="MISSION" value={missionCount > 0 ? `${missionCount} ACTIVE` : 'IDLE'} />
          </div>
        </div>

        {/* Center column: Subtle state-reactive chest halo, ambient energy, and pulse traces */}
        <div className="hero-core-visual">
          <AmbientEnergy state={state} />
          <div
            className="subtle-reactor"
            data-testid="subtle-reactor"
            aria-label="Subtle JARVIS reactor overlay"
          >
            <HolographicCore state={state} label="JARVIS CORE" size={132} concept="halo" />
            <span className="reactor-orbit orbit-one" />
            <span className="reactor-orbit orbit-two" />
            <span className="reactor-trace trace-left" />
            <span className="reactor-trace trace-right" />
          </div>
          <PulseNetwork nodes={networkNodes} active={state !== 'offline'} />
          <JWaveform active={speaking || ['thinking', 'tool', 'researching'].includes(state)} />
        </div>

        {/* Right column: Floating situational context telemetry */}
        <div className="hero-readouts">
          <div className="hero-context-float">
            <HoloLabel>OWNER CONTEXT</HoloLabel>
            <strong className="context-window-text">{focusedWindow}</strong>
            <small className="context-app-text">{application}</small>
            <CompassStrip label="FOCUS VECTOR" value={String(focusedWindow)} />
          </div>

          <div className={`hero-context-float attention-float ${attentionCount ? 'has-attention' : ''}`}>
            <HoloLabel>ATTENTION FIELD</HoloLabel>
            <strong className="attention-status-text">
              {attentionCount ? `${attentionCount} PENDING` : 'ALL CLEAR'}
            </strong>
            <small className="attention-detail-text">
              {attentionCount ? 'Approval checkpoint required' : 'No pending approvals'}
            </small>
          </div>

          <RadarSweep points={deviceCount} label="DEVICE FIELD" />
        </div>
      </div>

      {/* Bottom telemetry ribbon */}
      <div className="hero-ribbon">
        <span>LOCAL OPERATIONS</span>
        <i />
        <span>MISSION FIELD {missionCount > 0 ? `${missionCount} ACTIVE` : 'IDLE'}</span>
        <i />
        <span>DEVICE FIELD {deviceCount}</span>
        <i />
        <span>OWNER ATTENTION {attentionCount ? 'REQUIRED' : 'CLEAR'}</span>
      </div>
    </section>
  )
}

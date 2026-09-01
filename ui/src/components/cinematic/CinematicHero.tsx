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
  modelLabel: string
  description: string
  focusedWindow: ReactNode
  application: ReactNode
  missionCount: number
  attentionCount: number
  voiceState: string
  deviceCount?: number
}

export function CinematicHero({ wallpaper, state, modelLabel, description, focusedWindow, application, missionCount, attentionCount, voiceState, deviceCount = 0 }: CinematicHeroProps) {
  const speaking = ['listening', 'speaking', 'responding'].includes(voiceState.toLowerCase())
  const networkNodes: PulseNetworkNode[] = [
    { label: 'CORE', state },
    { label: 'VOICE', state: speaking ? 'speaking' : 'idle' },
    { label: 'MISSION', state: missionCount ? 'tool' : 'idle' },
  ]
  return <section className={`cinematic-hero visual-state-${state}`} data-testid="cinematic-hero" data-visual-state={state} aria-label="JARVIS cinematic command scene">
    <div className="hero-art" data-testid="hero-art" style={{ backgroundImage: `url(${wallpaper})` }} />
    <div className="hero-art-shade" /><DepthGrid /><ScanPlane /><CinematicBoot state={state} />
    <div className="hero-scene">
      <div className="hero-copy">
        <HoloLabel>JARVIS // CINEMATIC OPERATIONS</HoloLabel>
        <div className="hero-state-line"><span className="hero-state" data-testid="hero-state">{state.replaceAll('_', ' ').toUpperCase()}</span><span>LOCAL SCENE</span></div>
        <h2>{modelLabel}</h2><p>{description}</p>
        <div className="hero-signal-row"><DataArc label="CORE" value={state.replaceAll('_', ' ').toUpperCase()} /><DataArc label="VOICE" value={voiceState || 'sleeping'} /><DataArc label="MISSION" value={missionCount || 'IDLE'} /></div>
      </div>
      <div className="hero-core-visual">
        <AmbientEnergy />
        <div className="subtle-reactor" data-testid="subtle-reactor" aria-label="Subtle JARVIS reactor overlay"><HolographicCore state={state} label="JARVIS CORE" size={132} /><span className="reactor-orbit orbit-one" /><span className="reactor-orbit orbit-two" /></div>
        <PulseNetwork nodes={networkNodes} active={state !== 'offline'} />
        <JWaveform active={speaking || ['thinking', 'tool', 'researching'].includes(state)} />
      </div>
      <div className="hero-readouts">
        <div className="hero-context-float"><HoloLabel>OWNER CONTEXT</HoloLabel><strong>{focusedWindow}</strong><small>{application}</small><CompassStrip label="FOCUS VECTOR" value={String(focusedWindow)} /></div>
        <div className="hero-context-float attention-float"><HoloLabel>ATTENTION FIELD</HoloLabel><strong>{attentionCount || 'CLEAR'}</strong><small>{attentionCount ? 'Approval checkpoint' : 'No pending approvals'}</small></div>
        <RadarSweep points={deviceCount} label="DEVICE FIELD" />
      </div>
    </div>
    <div className="hero-ribbon"><span>LOCAL OPERATIONS</span><i /><span>MISSION FIELD {missionCount || 'IDLE'}</span><i /><span>DEVICE FIELD {deviceCount}</span><i /><span>OWNER CONTROL {attentionCount ? 'REQUIRED' : 'READY'}</span></div>
  </section>
}

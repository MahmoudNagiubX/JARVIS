import { useId, useMemo } from 'react'
import type { JarvisVisualState } from '../../features/core/deriveVisualState'

const TICK_ANGLES = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330] as const

export interface HoloRingProps {
  state?: JarvisVisualState
  label?: string
  size?: number
  concept?: 'halo' | 'orb' | 'traces'
}

function getRingSpeeds(state: JarvisVisualState): { r1: string; r2: string; r3: string } {
  switch (state) {
    case 'thinking':
      return { r1: '2s', r2: '1.2s', r3: '1.8s' }
    case 'tool':
    case 'researching':
      return { r1: '3s', r2: '1.8s', r3: '2.4s' }
    case 'waiting_approval':
      return { r1: '4s', r2: '2.5s', r3: '3s' }
    case 'speaking':
      return { r1: '4s', r2: '2.8s', r3: '3.6s' }
    case 'degraded':
      return { r1: '12s', r2: '9s', r3: '14s' }
    case 'offline':
      return { r1: '0s', r2: '0s', r3: '0s' }
    case 'error':
      return { r1: '1.5s', r2: '1s', r3: '1.2s' }
    case 'idle':
    case 'ready':
    default:
      return { r1: '8s', r2: '5s', r3: '7s' }
  }
}

/**
 * HoloRing adapts concrete geometry from:
 * - Donor 03 JOrb.tsx (12 precomputed 30-deg tick marks, multi-ring timing)
 * - Donor 07 ArcReactor.tsx (3 120-deg energy arms, core radial gradient)
 * - Donor 08 ironman-hud.html (tactical hexagonal reticle, degree markers)
 */
export function HoloRing({ state = 'ready', label = 'JARVIS CORE', size = 132, concept = 'halo' }: HoloRingProps) {
  const id = useId().replaceAll(':', '')
  const glowId = `holo-ring-glow-${id}`
  const gradId = `holo-core-grad-${id}`
  const speeds = useMemo(() => getRingSpeeds(state), [state])

  return (
    <div
      className={`holo-ring-unit holo-state-${state} holo-concept-${concept}`}
      data-testid="holo-ring"
      data-state={state}
      data-concept={concept}
      data-reduced-motion="supported"
      style={{ width: size, height: size }}
      aria-label={`${label}: ${state}`}
      role="img"
    >
      <svg viewBox="0 0 120 120" aria-hidden="true" className="holo-ring-svg">
        <defs>
          <filter id={glowId} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="1.8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <radialGradient id={gradId} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.8" />
            <stop offset="60%" stopColor="currentColor" stopOpacity="0.25" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* 12 tick marks at 30° intervals adapted from Donor 03 JOrb */}
        {TICK_ANGLES.map((angle) => {
          const rad = (angle * Math.PI) / 180
          const r1 = 54
          const r2 = 57
          const x1 = 60 + r1 * Math.sin(rad)
          const y1 = 60 - r1 * Math.cos(rad)
          const x2 = 60 + r2 * Math.sin(rad)
          const y2 = 60 - r2 * Math.cos(rad)
          return (
            <line
              key={angle}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              className="holo-ring-tick"
              data-testid="holo-tick"
            />
          )
        })}

        {/* Outer dashed spinning ring */}
        <circle
          className="holo-ring-track"
          cx="60"
          cy="60"
          r="51"
          style={{ animationDuration: speeds.r1 }}
        />

        {/* Tactical dash ring with glow filter */}
        <circle
          className="holo-ring-dash"
          cx="60"
          cy="60"
          r="45"
          filter={`url(#${glowId})`}
          style={{ animationDuration: speeds.r2 }}
        />

        {/* Hexagonal inner reticle adapted from Donor 08 / Donor 07 */}
        <polygon
          points="60,26 89,43 89,77 60,94 31,77 31,43"
          className="holo-ring-hex"
          filter={`url(#${glowId})`}
        />

        {/* Inner rotating ring */}
        <circle
          className="holo-ring-inner"
          cx="60"
          cy="60"
          r="32"
          style={{ animationDuration: speeds.r3 }}
        />

        {/* 3 energy arms at 120° intervals adapted from Donor 07 ArcReactor */}
        {[0, 120, 240].map((deg) => {
          const rad = ((deg - 90) * Math.PI) / 180
          const x2 = 60 + 20 * Math.cos(rad)
          const y2 = 60 + 20 * Math.sin(rad)
          return (
            <line
              key={deg}
              x1="60"
              y1="60"
              x2={x2}
              y2={y2}
              className="holo-ring-arm"
              filter={`url(#${glowId})`}
            />
          )
        })}

        {/* Crosshair precision marks */}
        <path
          className="holo-ring-cross"
          d="M60 17v8 M60 95v8 M17 60h8 M95 60h8"
        />

        {/* Core glow radial gradient */}
        <circle
          className="holo-ring-core-glow"
          cx="60"
          cy="60"
          r="14"
          fill={`url(#${gradId})`}
        />

        {/* Core center node */}
        <circle
          className="holo-ring-core"
          cx="60"
          cy="60"
          r="6"
          filter={`url(#${glowId})`}
        />
      </svg>
      {label && <span className="holo-ring-label">{label}</span>}
    </div>
  )
}

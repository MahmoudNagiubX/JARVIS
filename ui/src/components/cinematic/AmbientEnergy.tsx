import type { JarvisVisualState } from '../../features/core/deriveVisualState'

export interface AmbientEnergyProps {
  state?: JarvisVisualState
}

/**
 * AmbientEnergy adapts the upward drift and fading particles from
 * Donor 07 ParticleField.tsx and Donor 09 spawnPing / randomGreatCircle.
 * Bounded to CSS/SVG without heavy canvas or remote scripts.
 */
export function AmbientEnergy({ state = 'ready' }: AmbientEnergyProps) {
  return (
    <span
      className={`ambient-energy ambient-state-${state}`}
      data-testid="ambient-energy"
      aria-hidden="true"
    >
      <i className="energy-spark spark-1" />
      <i className="energy-spark spark-2" />
      <i className="energy-spark spark-3" />
      <i className="energy-spark spark-4" />
      <i className="energy-spark spark-5" />
      <i className="energy-spark spark-6" />
      <span className="energy-halo" />
    </span>
  )
}

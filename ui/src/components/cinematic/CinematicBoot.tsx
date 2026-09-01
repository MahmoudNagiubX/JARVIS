import type { JarvisVisualState } from '../../features/core/deriveVisualState'

export function CinematicBoot({ state }: { state: JarvisVisualState }) {
  return (
    <span className="cinematic-boot" data-testid="cinematic-boot" aria-hidden="true">
      <i className="boot-pulse-pip" />
      <span className="boot-scene-text">SCENE // {state.replaceAll('_', ' ').toUpperCase()}</span>
      <span className="boot-sub-indicator" />
    </span>
  )
}

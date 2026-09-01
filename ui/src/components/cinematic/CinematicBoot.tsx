import type { JarvisVisualState } from '../../features/core/deriveVisualState'

export function CinematicBoot({ state }: { state: JarvisVisualState }) {
  return <span className="cinematic-boot" data-testid="cinematic-boot" aria-hidden="true"><i />SCENE // {state.replaceAll('_', ' ').toUpperCase()}</span>
}

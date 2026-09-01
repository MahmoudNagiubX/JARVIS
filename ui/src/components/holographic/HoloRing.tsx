import { useId } from 'react'
import type { JarvisVisualState } from '../../features/core/deriveVisualState'

export function HoloRing({ state = 'ready', label = 'JARVIS CORE', size = 132 }: { state?: JarvisVisualState; label?: string; size?: number }) {
  const id = useId().replaceAll(':', '')
  const glowId = `holo-ring-glow-${id}`
  return <div className={`holo-ring-unit holo-state-${state}`} data-testid="holo-ring" data-state={state} data-reduced-motion="supported" style={{ width: size, height: size }} aria-label={`${label}: ${state}`} role="img">
    <svg viewBox="0 0 120 120" aria-hidden="true">
      <defs><filter id={glowId}><feGaussianBlur stdDeviation="1.8" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs>
      <circle className="holo-ring-track" cx="60" cy="60" r="53" />
      <circle className="holo-ring-dash" cx="60" cy="60" r="47" filter={`url(#${glowId})`} />
      <circle className="holo-ring-inner" cx="60" cy="60" r="34" />
      <path className="holo-ring-cross" d="M60 19v10M60 91v10M19 60h10M91 60h10" />
      <circle className="holo-ring-core" cx="60" cy="60" r="9" filter={`url(#${glowId})`} />
    </svg>
    <span>{label}</span>
  </div>
}

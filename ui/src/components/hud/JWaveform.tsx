import type { CSSProperties } from 'react'

/** Adapted from donor 03 JWaveform (MIT); the bars communicate reported voice state only. */
export function JWaveform({ active = false }: { active?: boolean }) {
  return <div className={`waveform ${active ? 'active' : ''}`} aria-hidden="true">{Array.from({ length: 18 }, (_, index) => <i key={index} style={{ '--wave-height': `${8 + ((index * 7) % 17)}px` } as CSSProperties} />)}</div>
}

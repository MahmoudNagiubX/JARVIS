const POINT_POSITIONS = [
  [31, 27], [70, 34], [60, 68], [27, 67], [78, 73], [45, 48], [20, 48], [74, 56],
] as const

function pointPosition(index: number): readonly [number, number] {
  const known = POINT_POSITIONS[index]
  if (known) return known
  const angle = (index * 137.5 * Math.PI) / 180
  const radius = 22 + ((index * 17) % 20)
  return [Math.round(50 + Math.cos(angle) * radius), Math.round(50 + Math.sin(angle) * radius)]
}

export function RadarSweep({ points = 0, label = 'DEVICE FIELD', testId = 'radar-sweep' }: { points?: number; label?: string; testId?: string }) {
  const reported = Math.max(0, Math.floor(points))
  return <div className="radar-sweep" data-testid={testId} data-reported-points={reported} aria-label={`${label}: ${reported} reported points`}>
    <svg viewBox="0 0 100 100" role="img" aria-label={label}>
      <circle className="radar-ring" cx="50" cy="50" r="41" /><circle className="radar-ring" cx="50" cy="50" r="28" /><circle className="radar-ring" cx="50" cy="50" r="14" /><path className="radar-cross" d="M9 50h82M50 9v82" /><path className="radar-sweep-line" d="M50 50L50 9" />
      {Array.from({ length: reported }, (_, index) => pointPosition(index)).map(([cx, cy], index) => <circle className="radar-point" data-testid="radar-point" key={`${cx}-${cy}-${index}`} cx={cx} cy={cy} r="2" />)}
    </svg>
    <span>{reported ? `${reported} REPORTED` : 'SCANNER IDLE'}</span><small>{label}</small>
  </div>
}

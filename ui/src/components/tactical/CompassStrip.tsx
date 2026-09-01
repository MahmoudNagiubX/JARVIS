export function CompassStrip({ label = 'FOCUSED WINDOW', value = 'Not observed' }: { label?: string; value?: string }) {
  return <div className="compass-strip" aria-label={`${label}: ${value}`}><div><span>N</span><i /><span>NE</span><i /><span>E</span><i /><span>SE</span><i /><span>S</span></div><strong>{value}</strong><small>{label}</small></div>
}

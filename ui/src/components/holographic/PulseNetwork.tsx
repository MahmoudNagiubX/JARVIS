import type { JarvisVisualState } from '../../features/core/deriveVisualState'

export interface PulseNetworkNode {
  label: string
  state?: JarvisVisualState | string
}

export function PulseLink({ active = true }: { active?: boolean }) {
  return <span className={`pulse-link ${active ? 'is-active' : ''}`.trim()} aria-hidden="true" />
}

export function PulseNetwork({ nodes, active = true }: { nodes: PulseNetworkNode[]; active?: boolean }) {
  return <div className={`pulse-network ${active ? 'is-active' : ''}`.trim()} data-testid="hero-pulse-network" aria-label="Reported capability connections">
    {nodes.map((node) => <div className="pulse-network-node" key={node.label}><span className={`pulse-node-dot ${node.state ? `state-${node.state}` : ''}`} /><span>{node.label}</span></div>)}
    <PulseLink active={active} />
  </div>
}

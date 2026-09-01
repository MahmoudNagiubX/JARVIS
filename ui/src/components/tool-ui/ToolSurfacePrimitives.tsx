import { useState, type ReactNode } from 'react'
import type { JsonRecord } from '../../lib/format'
import { dateValue, stringValue, tone } from '../../lib/format'

/**
 * Adapted from donor 06_tool_ui ApprovalCard, CitationList, DataTable,
 * CodeBlock, StatsDisplay, Plan, ProgressTracker, and ToolFallback. All
 * content is inert display text; canonical JARVIS endpoints remain the only
 * action authority.
 */
export function ApprovalSurface({ approval, onDecision, interactive = true }: { approval: JsonRecord; onDecision: (approved: boolean) => Promise<void>; interactive?: boolean }) {
  const [state, setState] = useState('pending')
  const status = stringValue(approval.status, 'pending')
  const actionable = status === 'pending' && Boolean(stringValue(approval.run_id || approval.pending_run_id, '')) && interactive
  async function decide(approved: boolean) { setState('saving'); try { await onDecision(approved); setState('sent') } catch { setState('pending') } }
  return <article className="approval-surface"><div className="approval-head"><div><span className="eyebrow">OWNER DECISION</span><h3>{stringValue(approval.action, 'Consequential action')}</h3></div><span className={`approval-risk ${tone(approval.risk || status)}`}>{stringValue(approval.risk, status)}</span></div><p>{stringValue(approval.reason, 'The action requires owner confirmation.')}</p>{Boolean(approval.target) && <div className="approval-target"><span>EXACT TARGET</span><strong>{stringValue(approval.target)}</strong></div>}{Boolean(approval.preview) && <div className="approval-preview"><span>SANITIZED PREVIEW</span><p>{stringValue(approval.preview)}</p></div>}{status === 'pending' && <div className="approval-actions">{actionable ? <><button className="button primary" disabled={state === 'saving'} onClick={() => void decide(true)}>{state === 'saving' ? 'Saving…' : 'Approve'}</button><button className="button danger" disabled={state === 'saving'} onClick={() => void decide(false)}>Deny</button></> : <span className="small muted">Awaiting server run correlation</span>}</div>}</article>
}

export function CitationSurface({ evidence }: { evidence: JsonRecord[] }) {
  return <div className="citation-surface"><div className="tool-surface-head"><span className="eyebrow">EVIDENCE</span><strong>{evidence.length} sources</strong></div>{evidence.length ? evidence.map((item, index) => <article className="citation-row" key={stringValue(item.evidence_id || item.id, String(index))}><span className="citation-index">{String(index + 1).padStart(2, '0')}</span><div><strong>{stringValue(item.title || item.source, 'Local source')}</strong><p>{stringValue(item.excerpt || item.content, 'No excerpt')}</p><small>{stringValue(item.url, 'Persisted local evidence')}</small></div></article>) : <div className="compact-empty">No persisted evidence for this run.</div>}</div>
}

export function DataTable({ columns, rows }: { columns: string[]; rows: JsonRecord[] }) {
  return <div className="data-table-wrap"><table className="data-table"><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={stringValue(row.id || row.event_id || row.device_id, String(index))}>{columns.map((column) => <td key={column}>{stringValue(row[column], '—')}</td>)}</tr>)}</tbody></table></div>
}

export function CodeSurface({ code, filename = 'local-output.txt' }: { code: string; filename?: string }) {
  return <div className="code-surface"><div className="code-head"><span>{filename}</span><span>READ ONLY</span></div><pre><code>{code}</code></pre></div>
}

export function ToolFallbackSurface({ name, result }: { name: string; result: ReactNode }) {
  return <div className="tool-fallback-surface"><span className="eyebrow">TOOL RESULT</span><strong>{name}</strong><p>{result}</p></div>
}

export function StatsSurface({ items }: { items: Array<{ label: string; value: ReactNode; detail?: string }> }) {
  return <div className="stats-surface">{items.map((item) => <div key={item.label}><span>{item.label}</span><strong>{item.value}</strong>{item.detail && <small>{item.detail}</small>}</div>)}</div>
}

export function SafeTimestamp({ value }: { value: unknown }) {
  return <time className="safe-timestamp">{dateValue(value)}</time>
}

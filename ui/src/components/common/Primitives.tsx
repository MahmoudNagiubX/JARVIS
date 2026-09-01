import { isValidElement, type ReactNode } from 'react'
import { jsonText, stringValue, tone } from '../../lib/format'

export function Panel({ children, className = '', as: Tag = 'section' }: { children: ReactNode; className?: string; as?: 'section' | 'div' | 'article' }) {
  return <Tag className={`panel ${className}`.trim()}>{children}</Tag>
}

export function FramePanel({ children, title, eyebrow, status, className = '' }: { children: ReactNode; title?: string; eyebrow?: string; status?: unknown; className?: string }) {
  return <Panel className={`frame-panel ${className}`.trim()}>
    {(title || eyebrow || status !== undefined) && <div className="panel-head">
      <div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}{title && <h2>{title}</h2>}</div>
      {status !== undefined && <StatusBadge value={status} />}
    </div>}
    {children}
  </Panel>
}

export function StatusBadge({ value, label }: { value: unknown; label?: string }) {
  const valueText = stringValue(value, 'unknown')
  return <span className={`badge ${tone(valueText)}`}><span className="badge-dot" aria-hidden="true" />{label || valueText.replaceAll('_', ' ')}</span>
}

export function Metric({ label, value, status }: { label: string; value: unknown; status?: unknown }) {
  return <div className="metric"><span className="metric-label">{label}</span><strong className={tone(status ?? value)}>{stringValue(value)}</strong></div>
}

export function DetailList({ values }: { values: Record<string, unknown> }) {
  return <dl className="detail-list">{Object.entries(values).map(([key, value]) => <div className="detail-row" key={key}><dt>{key}</dt><dd className={tone(value)}>{isValidElement(value) ? value : jsonText(value)}</dd></div>)}</dl>
}

export function SectionHeading({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="page-heading"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1>{description && <p className="lede">{description}</p>}</div>{action && <div className="heading-action">{action}</div>}</div>
}

export function EmptyState({ title, detail, action }: { title: string; detail?: string; action?: ReactNode }) {
  return <div className="empty-state"><span className="empty-mark" aria-hidden="true">∅</span><strong>{title}</strong>{detail && <p>{detail}</p>}{action}</div>
}

export function LoadingState({ label = 'Loading authoritative state…' }: { label?: string }) {
  return <div className="state-block loading-state" role="status"><span className="loader" aria-hidden="true" />{label}</div>
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="state-block error-state" role="alert"><strong>Local service unavailable</strong><p>{message}</p>{onRetry && <button className="button secondary" onClick={onRetry}>Retry</button>}</div>
}

export function Button({ children, variant = 'secondary', type = 'button', disabled, onClick, title }: { children: ReactNode; variant?: 'primary' | 'secondary' | 'danger' | 'quiet'; type?: 'button' | 'submit' | 'reset'; disabled?: boolean; onClick?: () => void; title?: string }) {
  return <button className={`button ${variant}`} type={type} disabled={disabled} onClick={onClick} title={title}>{children}</button>
}

export function ListCard({ title, status, meta, children, actions }: { title: string; status?: unknown; meta?: string; children?: ReactNode; actions?: ReactNode }) {
  return <Panel className="list-card"><div className="card-heading"><div><h3>{title}</h3>{meta && <span className="muted small">{meta}</span>}</div>{status !== undefined && <StatusBadge value={status} />}</div>{children && <div className="card-body">{children}</div>}{actions && <div className="card-actions">{actions}</div>}</Panel>
}

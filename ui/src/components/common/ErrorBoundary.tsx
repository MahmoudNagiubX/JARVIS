import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from './Primitives'

interface Props { children: ReactNode }
interface State { failed: boolean }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State { return { failed: true } }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Keep render failures local to the UI. Do not log payloads or credentials.
  }

  render() {
    if (!this.state.failed) return this.props.children
    return <div className="state-block error-state" role="alert"><strong>This panel could not render</strong><p>The local runtime remains protected. Refresh the Command Center to rebuild the view from server state.</p><Button variant="secondary" onClick={() => window.location.reload()}>Reload view</Button></div>
  }
}

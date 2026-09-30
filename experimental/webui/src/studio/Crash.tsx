/* The Studio's last resort: an error thrown while rendering would otherwise
   unmount the whole page and leave it blank, so the error and the component
   it came from are shown instead, with a way back. */

import { Component } from 'react'

import { T } from './copy'

import type { ErrorInfo, JSX, ReactNode } from 'react'

interface State {
  error: Error | null
  stack: string
}

export class Crash extends Component<{ children: ReactNode }, State> {
  state: State = { error: null, stack: '' }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Studio render error', error, info.componentStack)
    this.setState({ stack: info.componentStack ?? '' })
  }

  render(): JSX.Element | ReactNode {
    const { error, stack } = this.state
    if (!error) return this.props.children
    return (
      <div className="st-crash" role="alert">
        <h2>{T.crashTitle}</h2>
        <p className="st-quiet">{T.crashNote}</p>
        <pre>{`${error.name}: ${error.message}\n${error.stack ?? ''}${stack ? `\n\n${stack.trim()}` : ''}`}</pre>
        <div className="st-crash-actions">
          <button type="button" className="st-btn primary" onClick={() => this.setState({ error: null, stack: '' })}>{T.crashRetry}</button>
          <button type="button" className="st-btn" onClick={() => window.location.reload()}>{T.crashReload}</button>
        </div>
      </div>
    )
  }
}

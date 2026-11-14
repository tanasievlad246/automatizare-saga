import { Component } from 'react'
import type { ReactNode } from 'react'
import { Notice } from './Notice'

/**
 * If a screen fails to draw, say so and keep the menu usable, instead of leaving a blank
 * page. Give it a `key` that changes with the address, so going elsewhere starts afresh.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <Notice tone="attention">
        <p className="font-semibold">Această pagină nu a putut fi afișată.</p>
        <p>Alegeți altă pagină din meniu sau reîncărcați (tasta F5).</p>
      </Notice>
    )
  }
}

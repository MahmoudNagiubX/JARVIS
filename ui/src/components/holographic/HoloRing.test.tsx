import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HoloRing } from './HoloRing'

describe('HoloRing', () => {
  it('exposes state-driven motion semantics with a reduced-motion fallback', () => {
    render(<HoloRing state="thinking" label="JARVIS CORE" />)
    expect(screen.getByTestId('holo-ring')).toHaveAttribute('data-state', 'thinking')
    expect(screen.getByTestId('holo-ring')).toHaveAttribute('data-reduced-motion', 'supported')
    expect(screen.getByText('JARVIS CORE')).toBeInTheDocument()
  })
})

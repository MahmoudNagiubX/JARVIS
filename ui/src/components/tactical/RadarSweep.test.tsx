import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RadarSweep } from './RadarSweep'

describe('RadarSweep', () => {
  it('shows an idle scanner when the backend reports no points', () => {
    render(<RadarSweep points={0} label="DEVICE FIELD" />)
    expect(screen.getByTestId('radar-sweep')).toHaveAttribute('data-reported-points', '0')
    expect(screen.getByText('SCANNER IDLE')).toBeInTheDocument()
  })

  it('renders exactly the number of real points supplied by the projection', () => {
    render(<RadarSweep points={2} label="DEVICE FIELD" />)
    expect(screen.getAllByTestId('radar-point')).toHaveLength(2)
  })

  it('does not silently drop reported devices beyond the starter coordinate set', () => {
    render(<RadarSweep points={9} label="DEVICE FIELD" />)
    expect(screen.getAllByTestId('radar-point')).toHaveLength(9)
  })
})

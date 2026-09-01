import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CinematicHero } from './CinematicHero'

describe('CinematicHero', () => {
  it('anchors the owner wallpaper, presents JARVIS as primary identity, and excludes model labels', () => {
    render(
      <CinematicHero
        wallpaper="/app/assets/ironman-owner-wallpaper.jpg"
        state="ready"
        description="Local runtime connected."
        focusedWindow="Command Center"
        application="JARVIS"
        missionCount={2}
        attentionCount={0}
        voiceState="sleeping"
      />
    )

    expect(screen.getByTestId('cinematic-hero')).toHaveAttribute('data-visual-state', 'ready')
    expect(screen.getByTestId('hero-art')).toHaveStyle({ backgroundImage: 'url(/app/assets/ironman-owner-wallpaper.jpg)' })
    expect(screen.getByRole('heading', { level: 2, name: 'JARVIS' })).toBeInTheDocument()
    expect(screen.queryByText('local-qwen')).not.toBeInTheDocument()
    expect(screen.queryByText('jarvis-local-qwen')).not.toBeInTheDocument()
    expect(screen.getByTestId('subtle-reactor')).toBeInTheDocument()
    expect(screen.queryByTestId('hero-reactor')).not.toBeInTheDocument()
    expect(screen.getByTestId('hero-state')).toHaveTextContent('READY')
    expect(screen.getByTestId('hero-status-badge')).toHaveTextContent('READY')
    expect(screen.getByTestId('hero-pulse-network')).toBeInTheDocument()
  })

  it('renders sparse/offline data honestly without fabricated telemetry or nominal labels', () => {
    render(
      <CinematicHero
        wallpaper="/app/assets/ironman-owner-wallpaper.jpg"
        state="offline"
        description="Local capabilities remain available."
        focusedWindow="Not observed"
        application="No active application"
        missionCount={0}
        attentionCount={0}
        voiceState="sleeping"
      />
    )

    expect(screen.getByText('SCENE // OFFLINE')).toBeInTheDocument()
    expect(screen.getByTestId('hero-status-badge')).toHaveTextContent('LOCAL ONLY')
    expect(screen.queryByText('SYSTEMS NOMINAL')).not.toBeInTheDocument()
    expect(screen.getByText('No active application')).toBeInTheDocument()
    expect(screen.getByText('MISSION FIELD', { exact: false })).toBeInTheDocument()
    expect(screen.queryByText('local-qwen')).not.toBeInTheDocument()
    expect(screen.queryByText('jarvis-local-qwen')).not.toBeInTheDocument()
  })

  it('visibly updates visual state data attributes and telemetry when state changes', () => {
    render(
      <CinematicHero
        wallpaper="/app/assets/ironman-owner-wallpaper.jpg"
        state="waiting_approval"
        focusedWindow="Terminal"
        application="VSCode"
        missionCount={1}
        attentionCount={3}
        voiceState="speaking"
      />
    )

    expect(screen.getByTestId('cinematic-hero')).toHaveAttribute('data-visual-state', 'waiting_approval')
    expect(screen.getByTestId('hero-state')).toHaveTextContent('WAITING APPROVAL')
    expect(screen.getByTestId('hero-status-badge')).toHaveTextContent('ATTENTION')
    expect(screen.getByText('3 PENDING')).toBeInTheDocument()
    expect(screen.getByText('Approval checkpoint required')).toBeInTheDocument()
  })
})

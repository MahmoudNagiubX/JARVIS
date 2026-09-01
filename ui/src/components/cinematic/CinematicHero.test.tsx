import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CinematicHero } from './CinematicHero'

describe('CinematicHero', () => {
  it('anchors the owner wallpaper and keeps the reactor treatment subtle', () => {
    render(<CinematicHero wallpaper="/app/assets/ironman-owner-wallpaper.jpg" state="ready" modelLabel="local-qwen" description="Local runtime connected." focusedWindow="Command Center" application="JARVIS" missionCount={2} attentionCount={0} voiceState="sleeping" />)

    expect(screen.getByTestId('cinematic-hero')).toHaveAttribute('data-visual-state', 'ready')
    expect(screen.getByTestId('hero-art')).toHaveStyle({ backgroundImage: 'url(/app/assets/ironman-owner-wallpaper.jpg)' })
    expect(screen.getByTestId('subtle-reactor')).toBeInTheDocument()
    expect(screen.queryByTestId('hero-reactor')).not.toBeInTheDocument()
    expect(screen.getByTestId('hero-state')).toHaveTextContent('READY')
    expect(screen.getByTestId('hero-pulse-network')).toBeInTheDocument()
  })

  it('renders sparse data as explicit state instead of fabricating scene data', () => {
    render(<CinematicHero wallpaper="/app/assets/ironman-owner-wallpaper.jpg" state="offline" modelLabel="Local brain" description="Local capabilities remain available." focusedWindow="Not observed" application="No active application" missionCount={0} attentionCount={0} voiceState="sleeping" />)

    expect(screen.getByText('SCENE // OFFLINE')).toBeInTheDocument()
    expect(screen.getByText('No active application')).toBeInTheDocument()
    expect(screen.getByText('MISSION FIELD', { exact: false })).toBeInTheDocument()
  })
})

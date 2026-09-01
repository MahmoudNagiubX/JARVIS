import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import {
  ConfidenceMeter,
  ConversationRail,
  MissionPipeline,
  PlanSurface,
  ProgressSurface,
  RichMessage,
  RunInbox,
} from './OperationsPrimitives'

describe('OperationsPrimitives', () => {
  describe('ConversationRail', () => {
    it('renders conversation list with active indicators and handles selection', () => {
      const onSelect = vi.fn()
      const onNew = vi.fn()
      const conversations = [
        { id: 'conv-1', title: 'System Diagnostics', updated_at: '2026-09-01T10:00:00Z' },
        { id: 'conv-2', title: 'Tactical Recon', updated_at: '2026-09-01T11:00:00Z' },
      ]

      render(
        <ConversationRail
          conversations={conversations}
          selected="conv-1"
          onSelect={onSelect}
          onNew={onNew}
        />
      )

      expect(screen.getByTestId('conversation-rail')).toBeInTheDocument()
      expect(screen.getByText('System Diagnostics')).toBeInTheDocument()
      expect(screen.getByText('Tactical Recon')).toBeInTheDocument()

      fireEvent.click(screen.getByText('Tactical Recon'))
      expect(onSelect).toHaveBeenCalledWith('conv-2')

      fireEvent.click(screen.getByRole('button', { name: '+ New' }))
      expect(onNew).toHaveBeenCalled()
    })
  })

  describe('RichMessage', () => {
    it('renders user message with YOU role tag and clean typography', () => {
      render(
        <RichMessage
          message={{
            role: 'user',
            content: 'Initiate diagnostic scan.',
            created_at: '2026-09-01T12:00:00Z',
          }}
        />
      )

      expect(screen.getByText('YOU')).toBeInTheDocument()
      expect(screen.getByText('Initiate diagnostic scan.')).toBeInTheDocument()
    })

    it('renders JARVIS message with code blocks and expandable tool activity button', () => {
      const activity = [
        {
          tool_call_id: 'tool-1',
          name: 'system.scan',
          status: 'completed',
          args: { target: 'local_subsystems' },
          result: { healthy: true, latency_ms: 4 },
        },
      ]

      render(
        <RichMessage
          message={{
            role: 'assistant',
            content: 'Subsystems verified:\n```\n{"status": "nominal"}\n```',
            created_at: '2026-09-01T12:01:00Z',
          }}
          activity={activity}
        />
      )

      expect(screen.getByText('JARVIS')).toBeInTheDocument()
      expect(screen.getByText('{"status": "nominal"}')).toBeInTheDocument()
      expect(screen.getByTestId('message-tools')).toBeInTheDocument()
      expect(screen.getByText('system.scan')).toBeInTheDocument()
      expect(screen.getByText('completed')).toBeInTheDocument()

      const toolButton = screen.getByRole('button', { name: 'system.scan details' })
      expect(toolButton).toBeInTheDocument()
      expect(toolButton).toHaveAttribute('aria-expanded', 'false')

      // Expand tool details via click / button activation
      fireEvent.click(toolButton)
      expect(toolButton).toHaveAttribute('aria-expanded', 'true')
      expect(screen.getByText('INPUT')).toBeInTheDocument()
      expect(screen.getByText('OUTPUT')).toBeInTheDocument()
      expect(screen.getByText(/"healthy": true/)).toBeInTheDocument()

      // Collapse tool details
      fireEvent.click(toolButton)
      expect(toolButton).toHaveAttribute('aria-expanded', 'false')
      expect(screen.queryByText('INPUT')).not.toBeInTheDocument()
    })
  })

  describe('MissionPipeline', () => {
    it('categorizes missions into tactical lifecycle stages', () => {
      const missions = [
        { mission_id: 'm-1', title: 'Draft Plan', status: 'draft', current_step: 'Writing schema' },
        { mission_id: 'm-2', title: 'Active Patrol', status: 'active', current_step: 'Scanning network' },
        { mission_id: 'm-3', title: 'Review Gate', status: 'waiting_approval', current_step: 'Awaiting signoff' },
        { mission_id: 'm-4', title: 'Done Task', status: 'completed', current_step: 'Finished' },
      ]

      render(<MissionPipeline missions={missions} />)

      const pipeline = screen.getByTestId('mission-pipeline')
      expect(pipeline).toHaveTextContent('Draft Plan')
      expect(pipeline).toHaveTextContent('Active Patrol')
      expect(pipeline).toHaveTextContent('Review Gate')
      expect(pipeline).toHaveTextContent('Done Task')
      expect(pipeline).toHaveTextContent('planning')
      expect(pipeline).toHaveTextContent('active')
      expect(pipeline).toHaveTextContent('review')
      expect(pipeline).toHaveTextContent('closed')
    })
  })

  describe('PlanSurface', () => {
    it('renders tactical step indicators with numbers and completion markers', () => {
      const steps = [
        { label: 'Inspect local environment', status: 'completed' },
        { label: 'Execute verification tests', status: 'running' },
        { label: 'Compile release build', status: 'pending' },
      ]

      render(<PlanSurface title="Tactical Routine" steps={steps} />)

      expect(screen.getByText('EXECUTION PLAN')).toBeInTheDocument()
      expect(screen.getByText('Tactical Routine')).toBeInTheDocument()
      expect(screen.getByText('Inspect local environment')).toBeInTheDocument()
      expect(screen.getByText('Execute verification tests')).toBeInTheDocument()
      expect(screen.getByText('Compile release build')).toBeInTheDocument()
      expect(screen.getByText('✓')).toBeInTheDocument()
    })
  })

  describe('ProgressSurface', () => {
    it('renders progress percentage and bar variant', () => {
      render(<ProgressSurface label="Subsystem Readiness" value={85} status="running" />)

      expect(screen.getByText('Subsystem Readiness')).toBeInTheDocument()
      expect(screen.getByText('85%')).toBeInTheDocument()
    })

    it('renders ticks variant when requested', () => {
      const { container } = render(
        <ProgressSurface label="Power Matrix" value={50} variant="ticks" />
      )

      expect(screen.getByText('Power Matrix')).toBeInTheDocument()
      expect(screen.getByText('50%')).toBeInTheDocument()
      expect(container.querySelectorAll('.progress-tick').length).toBe(16)
    })
  })

  describe('ConfidenceMeter', () => {
    it('renders confidence percentage and active segments', () => {
      const { container } = render(<ConfidenceMeter value={80} />)

      expect(screen.getByTestId('confidence-meter')).toBeInTheDocument()
      expect(screen.getByText('80%')).toBeInTheDocument()
      expect(container.querySelectorAll('.confidence-segment.active').length).toBe(4)
    })

    it('scales ratio values between 0 and 1 correctly', () => {
      render(<ConfidenceMeter value={0.95} />)
      expect(screen.getByText('95%')).toBeInTheDocument()
    })

    it('displays fallback when value is not reported', () => {
      render(<ConfidenceMeter value={undefined} />)
      expect(screen.getByText('Not reported')).toBeInTheDocument()
    })
  })

  describe('RunInbox', () => {
    it('renders background runs list with status indicators', () => {
      const runs = [
        { run_id: 'run-101', title: 'Telemetry stream', state: 'running', created_at: '2026-09-01T12:00:00Z' },
      ]

      render(<RunInbox runs={runs} />)

      expect(screen.getByText('BACKGROUND INBOX')).toBeInTheDocument()
      expect(screen.getByText('1 tracked')).toBeInTheDocument()
      expect(screen.getByText('Telemetry stream')).toBeInTheDocument()
      expect(screen.getByText('running')).toBeInTheDocument()
    })
  })
})

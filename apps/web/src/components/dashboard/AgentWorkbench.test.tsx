import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { AgentWorkbench } from './AgentWorkbench';
import type { DebateMessage } from '../../lib/types';

const debate: DebateMessage[] = [
  {
    id: 'cycle-1-bull',
    timestamp: '2026-06-23T14:30:00Z',
    agent_id: 'BullResearcherAgent',
    stance: 'bull',
    message: 'Bull case for TSLA uses released evidence.',
    evidence_ids: ['event-1'],
    symbol: 'TSLA'
  },
  {
    id: 'cycle-1-bear',
    timestamp: '2026-06-23T14:30:00Z',
    agent_id: 'BearResearcherAgent',
    stance: 'bear',
    message: 'Bear case for TSLA highlights execution risk.',
    evidence_ids: ['event-1'],
    symbol: 'TSLA'
  },
  {
    id: 'cycle-2-bull',
    timestamp: '2026-06-23T14:45:00Z',
    agent_id: 'BullResearcherAgent',
    stance: 'bull',
    message: 'Bull case for AAPL is weaker.',
    evidence_ids: [],
    symbol: 'AAPL'
  },
  {
    id: 'cycle-2-bear',
    timestamp: '2026-06-23T14:45:00Z',
    agent_id: 'BearResearcherAgent',
    stance: 'bear',
    message: 'Bear case for AAPL prefers waiting.',
    evidence_ids: [],
    symbol: 'AAPL'
  }
];

test('groups debate entries by cycle and symbol', () => {
  render(<AgentWorkbench agents={[]} debate={debate} decisions={[]} />);

  fireEvent.click(screen.getByRole('button', { name: /Debate/i }));

  const aaplGroup = screen.getByText('AAPL').closest('article');
  const tslaGroup = screen.getByText('TSLA').closest('article');

  expect(aaplGroup).not.toBeNull();
  expect(tslaGroup).not.toBeNull();
  expect(within(aaplGroup as HTMLElement).getByText('BullResearcherAgent')).toBeInTheDocument();
  expect(within(aaplGroup as HTMLElement).getByText('BearResearcherAgent')).toBeInTheDocument();
  expect(within(tslaGroup as HTMLElement).getAllByText('event-1')).toHaveLength(2);
});

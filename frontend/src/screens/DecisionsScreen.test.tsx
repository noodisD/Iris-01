/**
 * The decision journal: record any decision with the facts that were never
 * written down before, then close it with how it went and whether you would
 * decide the same again.
 *
 * Every entry is invented.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Decision } from '@/types/api';

const server = vi.hoisted(() => ({
  decisions: [] as Decision[],
  created: [] as unknown[],
  outcomes: [] as unknown[],
  failNext: false,
}));

function stored(input: Partial<Decision> & { what: string }, id: string): Decision {
  return {
    id, decidedOn: '2024-05-10', stake: null, reversible: null, confidence: null, lastDays: null,
    pressures: [], sleepHours: null, energy: null, feeling: null, plan: null,
    outcome: null, followedPlan: null, wouldRepeat: null, closedAt: null, ...input,
  } as Decision;
}

vi.mock('@/api/decisions', () => ({
  getDecisions: async () => ({ decisions: server.decisions }),
  createDecision: async (input: Partial<Decision> & { what: string }) => {
    if (server.failNext) { server.failNext = false; throw new Error('the server is away'); }
    server.created.push(input);
    const d = stored(input, String(server.decisions.length + 1));
    server.decisions = [d, ...server.decisions];
    return d;
  },
  recordOutcome: async (id: string, input: Record<string, unknown>) => {
    server.outcomes.push({ id, ...input });
    server.decisions = server.decisions.map(d => d.id === id
      ? { ...d, ...input, closedAt: '2024-05-12T10:00:00Z' } as Decision : d);
    return server.decisions.find(d => d.id === id);
  },
}));

import { DecisionsScreen } from './DecisionsScreen';

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><DecisionsScreen /></QueryClientProvider>);
}

describe('recording a decision', () => {
  beforeEach(() => {
    server.decisions = []; server.created = []; server.outcomes = []; server.failNext = false;
  });

  it('needs only the first line, and sends every answer in its own shape', async () => {
    show();
    const record = await screen.findByRole('button', { name: 'Record decision' });
    expect(record).toBeDisabled();

    fireEvent.change(screen.getByLabelText('What'), { target: { value: 'Signed up for a marathon six weeks away' } });
    fireEvent.click(screen.getByRole('button', { name: 'more than I can afford to lose' }));
    fireEvent.click(screen.getByRole('button', { name: 'not at all' }));
    fireEvent.change(screen.getByLabelText('How sure (%)'), { target: { value: '35' } });
    fireEvent.click(screen.getByRole('button', { name: 'a setback' }));
    fireEvent.click(screen.getByRole('button', { name: 'a deadline' }));
    fireEvent.click(screen.getByRole('button', { name: 'a strong urge' }));
    fireEvent.change(screen.getByLabelText('Hours slept'), { target: { value: '5.5' } });
    fireEvent.click(screen.getByRole('button', { name: 'energy 3' }));
    fireEvent.click(screen.getByRole('button', { name: 'frustrated' }));
    fireEvent.change(screen.getByLabelText('Plan'), { target: { value: 'the long run in week three goes badly' } });
    fireEvent.click(record);

    await waitFor(() => expect(server.created).toHaveLength(1));
    expect(server.created[0]).toEqual({
      what: 'Signed up for a marathon six weeks away', stake: 'beyond_means', reversible: 'not_at_all',
      confidence: 35, lastDays: 'setback', pressures: ['deadline', 'urge'], sleepHours: 5.5, energy: 3,
      feeling: 'frustrated', plan: 'the long run in week three goes badly',
    });
    const open = await screen.findByRole('article', { name: /open decision: Signed up for a marathon/ });
    expect(within(open).getByText(/at stake: more than I can afford to lose · undo: not at all/)).toBeInTheDocument();
    expect(screen.getByLabelText('What')).toHaveValue('');
  });

  it('lets a pressure be chosen and unchosen, and sends none when none apply', async () => {
    show();
    fireEvent.change(await screen.findByLabelText('What'), { target: { value: 'Booked the train' } });
    const deadline = screen.getByRole('button', { name: 'a deadline' });
    fireEvent.click(deadline);
    expect(deadline).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(deadline);
    expect(deadline).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(screen.getByRole('button', { name: 'Record decision' }));
    await waitFor(() => expect(server.created).toHaveLength(1));
    expect((server.created[0] as { pressures: string[] }).pressures).toEqual([]);
  });

  it('keeps the draft and says so when saving fails', async () => {
    server.failNext = true;
    show();
    fireEvent.change(await screen.findByLabelText('What'), { target: { value: 'Stayed up to finish it' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record decision' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Not saved: the server is away');
    expect(screen.getByLabelText('What')).toHaveValue('Stayed up to finish it');
  });
});

describe('closing a decision', () => {
  beforeEach(() => {
    server.decisions = [stored({ what: 'Took the slower, safer route', plan: 'traffic clears' }, '7')];
    server.outcomes = [];
  });

  it('records how it went, the plan, and whether it would be decided the same, then closes it', async () => {
    show();
    const open = await screen.findByRole('article', { name: /open decision: Took the slower, safer route/ });
    fireEvent.change(within(open).getByLabelText(/How did it go/), { target: { value: 'Late, but calm' } });
    fireEvent.click(within(open).getByRole('button', { name: 'kept the plan' }));
    fireEvent.click(within(open).getByRole('button', { name: 'would decide the same' }));
    fireEvent.click(within(open).getByRole('button', { name: 'Close' }));

    await waitFor(() => expect(server.outcomes).toEqual([
      { id: '7', outcome: 'Late, but calm', followedPlan: 'yes', wouldRepeat: 'yes' }]));
    expect(await screen.findByText('Late, but calm')).toBeInTheDocument();
    expect(screen.getByText(/closed · 1/)).toBeInTheDocument();
    expect(screen.getByText('Nothing open.')).toBeInTheDocument();
  });
});

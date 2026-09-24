/**
 * The decision log: record a commitment with the facts that were never written
 * down before, then close it with how it went.
 *
 * Every entry is invented: a chess club.
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
    id, decidedOn: '2024-05-10', sharePct: null, borrowed: false, lastDays: null,
    moneyNeededFor: null, moneyNeededBy: null, sleepHours: null, energy: null, plan: null,
    outcome: null, followedPlan: null, closedAt: null, ...input,
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
  recordOutcome: async (id: string, input: { outcome: string; followedPlan?: string | null }) => {
    server.outcomes.push({ id, ...input });
    server.decisions = server.decisions.map(d => d.id === id
      ? { ...d, outcome: input.outcome, followedPlan: (input.followedPlan ?? null) as Decision['followedPlan'],
          closedAt: '2024-05-12T10:00:00Z' } : d);
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

  it('needs only the first line, and sends numbers as numbers and blanks not at all', async () => {
    show();
    const record = await screen.findByRole('button', { name: 'Record decision' });
    expect(record).toBeDisabled();

    fireEvent.change(screen.getByLabelText('What'), { target: { value: 'Entered every open tournament at once' } });
    fireEvent.change(screen.getByLabelText('Share of what you have (%)'), { target: { value: '140' } });
    fireEvent.click(screen.getByLabelText('some of it is borrowed'));
    fireEvent.click(screen.getByRole('button', { name: 'a big loss' }));
    fireEvent.change(screen.getByLabelText('Hours slept'), { target: { value: '5.5' } });
    fireEvent.click(screen.getByRole('button', { name: 'energy 3' }));
    fireEvent.change(screen.getByLabelText('Plan'), { target: { value: 'Withdraw after two losses' } });
    fireEvent.click(record);

    await waitFor(() => expect(server.created).toHaveLength(1));
    expect(server.created[0]).toEqual({
      what: 'Entered every open tournament at once', borrowed: true, sharePct: 140,
      lastDays: 'big_loss', moneyNeededFor: undefined, moneyNeededBy: undefined,
      sleepHours: 5.5, energy: 3, plan: 'Withdraw after two losses',
    });
    const open = await screen.findByRole('article', { name: /open decision: Entered every open tournament/ });
    expect(within(open).getByText(/140% · borrowed/)).toBeInTheDocument();
    expect(screen.getByLabelText('What')).toHaveValue('');
  });

  it('will not save a date for money without what it is needed for', async () => {
    show();
    fireEvent.change(await screen.findByLabelText('What'), { target: { value: 'Bought the new clock' } });
    fireEvent.change(screen.getByLabelText('Money needed by'), { target: { value: '2024-06-01' } });
    expect(screen.getByRole('button', { name: 'Record decision' })).toBeDisabled();
    expect(screen.getByText('Say what the money is needed for.')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Money needed for'), { target: { value: 'club fees' } });
    expect(screen.getByRole('button', { name: 'Record decision' })).toBeEnabled();
  });

  it('keeps the draft and says so when saving fails', async () => {
    server.failNext = true;
    show();
    fireEvent.change(await screen.findByLabelText('What'), { target: { value: 'Played blitz all night' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record decision' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Not saved: the server is away');
    expect(screen.getByLabelText('What')).toHaveValue('Played blitz all night');
  });
});

describe('closing a decision', () => {
  beforeEach(() => {
    server.decisions = [stored({ what: 'Offered an early draw', plan: 'Take it if refused twice' }, '7')];
    server.outcomes = [];
  });

  it('records how it went and whether the plan was kept, then moves it to closed', async () => {
    show();
    const open = await screen.findByRole('article', { name: /open decision: Offered an early draw/ });
    fireEvent.change(within(open).getByLabelText(/How did it go/), { target: { value: 'Declined, then lost' } });
    fireEvent.click(within(open).getByRole('button', { name: 'did not' }));
    fireEvent.click(within(open).getByRole('button', { name: 'Close' }));

    await waitFor(() => expect(server.outcomes).toEqual([
      { id: '7', outcome: 'Declined, then lost', followedPlan: 'no' }]));
    expect(await screen.findByText('Declined, then lost')).toBeInTheDocument();
    expect(screen.getByText(/closed · 1/)).toBeInTheDocument();
    expect(screen.getByText('Nothing open.')).toBeInTheDocument();
  });
});

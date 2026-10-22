import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import type { HealthLatest } from '@/types/api';

const state = vi.hoisted(() => ({ data: null as unknown }));
vi.mock('@/api/health', () => ({ getHealthLatest: async () => state.data }));

import { HealthBanner } from './HealthBanner';

function renderAt(path = '/today') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}>
    <HealthBanner /></MemoryRouter></QueryClientProvider>);
}

const run = (attention: HealthLatest['attention']): HealthLatest => ({
  runId: 'r1', runAt: '2026-10-22T07:30:00Z', counts: {}, attention });

beforeEach(() => { try { localStorage.clear(); } catch { /* none */ } });

it('says what needs attention and what waits on the owner, with details on request', async () => {
  state.data = run([{ id: 'queue.wasted', status: 'warn', summary: 'Failed attempts threw away 3 h.' },
    { id: 'owner.sensor_batches', status: 'waiting', summary: '2 phone batches wait.' }]);
  renderAt();
  expect(await screen.findByText('1 health check needs attention · 1 thing is waiting on you')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Details' }));
  expect(screen.getByText('Failed attempts threw away 3 h.')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Hide until next check' }));
  expect(screen.queryByLabelText('IRIS health')).toBeNull();
});

it('stays quiet when all is well, and off the chat screen', async () => {
  state.data = run([]);
  const quiet = renderAt();
  await new Promise(r => setTimeout(r, 20));
  expect(screen.queryByLabelText('IRIS health')).toBeNull();
  quiet.unmount();
  state.data = run([{ id: 'data.quotes', status: 'fail', summary: '2 quotes lost.' }]);
  renderAt('/chat');
  await new Promise(r => setTimeout(r, 20));
  expect(screen.queryByLabelText('IRIS health')).toBeNull();
});

it('says what IRIS repaired on its own, even when nothing else needs attention', async () => {
  state.data = { ...run([]), repaired: [{ id: 'data.orphan_embeddings', outcome: 'fixed',
    summary: 'Deleted 2 embedding(s) that pointed at deleted sources.' }] };
  renderAt();
  expect(await screen.findByText('IRIS repaired 1 thing itself')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Details' }));
  expect(screen.getByText('Deleted 2 embedding(s) that pointed at deleted sources.')).toBeTruthy();
});

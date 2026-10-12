import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import type { ChatEvidence } from '@/types/api';

const state = vi.hoisted(() => ({ added: false, newSince: 3, calls: 0 }));
vi.mock('@/hooks/useData', () => ({ useUser: () => ({ data: null }) }));
vi.mock('@/hooks/useTalk', () => ({ useTalk: () => ({ end: () => {}, start: async () => {} }) }));
vi.mock('@/api/chat', async importOriginal => {
  const actual = await importOriginal<object>();
  const status = (): ChatEvidence => ({ added: state.added, addedAt: null, messages: 3, yourMessages: 2,
    newSinceAdded: state.newSince, dollars: 0.0004,
    text: 'Adds this conversation to IRIS: your messages are read for patterns and ideas, IRIS\'s are only context.' });
  return {
    ...actual,
    getChatEvidence: async () => status(),
    addChatEvidence: async () => { state.calls += 1; state.added = true; state.newSince = 0; return status(); },
  };
});

import { AddToIris } from './ChatScreen';

function renderIt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>
    <AddToIris conversationId="c1" messageCount={3} busy={false} /></QueryClientProvider>);
}

it('shows the cost, adds only on the click, then says it is in IRIS', async () => {
  renderIt();
  const button = await screen.findByRole('button', { name: 'Add to IRIS' });
  expect(screen.getByText(/only context/)).toBeTruthy();
  expect(state.calls).toBe(0);
  fireEvent.click(button);
  await waitFor(() => expect(screen.getByRole('status').textContent).toContain('This conversation is in IRIS'));
  expect(state.calls).toBe(1);
});

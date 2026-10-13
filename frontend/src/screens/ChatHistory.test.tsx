import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import type * as ChatApi from '@/api/chat';

const calls = vi.hoisted(() => [] as string[]);
vi.mock('@/hooks/useData', () => ({ useUser: () => ({ data: null }) }));
vi.mock('@/hooks/useTalk', () => ({ useTalk: () => ({ end: () => {}, start: async () => {} }) }));
vi.mock('@/api/chat', async importOriginal => {
  const actual = await importOriginal<typeof ChatApi>();
  const convo = (id: string, n: number) => ({ id, userId: '1', startedAt: '2026-10-12T10:00:00Z',
    lastMessageAt: '2026-10-12T10:05:00Z', messageCount: n });
  return {
    ...actual,
    getCurrentConversation: async () => { calls.push('current'); return convo('last', 2); },
    getConversation: async (id: string) => { calls.push(`open:${id}`); return convo(id, 2); },
    startConversation: async () => { calls.push('start'); return convo('fresh', 0); },
    listConversations: async () => [
      { ...convo('last', 2), preview: 'The bus was late so I walked.', addedToIris: false },
      { ...convo('older', 4), preview: 'A quiet day at the allotment.', addedToIris: true }],
    getMessages: async (id: string) => id === 'fresh' ? [] : [
      { id: `${id}_0`, conversationId: id, role: 'user', text: `Said in ${id}`, createdAt: '2026-10-12T10:00:00Z' }],
    getChatEvidence: async () => ({ added: false, addedAt: null, messages: 1, yourMessages: 1, newSinceAdded: 1,
      dollars: 0.0004, text: '' }),
  };
});

import { ChatScreen } from './ChatScreen';

function Where() { return <p data-testid="where">{useLocation().search}</p>; }

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}>
    <Routes><Route path="/chat" element={<><ChatScreen /><Where /></>} /></Routes>
  </MemoryRouter></QueryClientProvider>);
}

it('reopens the conversation last written in, instead of starting over', async () => {
  calls.length = 0;
  renderAt('/chat');
  expect(await screen.findByText('Said in last')).toBeTruthy();
  expect(calls).toContain('current');
  expect(calls).not.toContain('start');
});

it('lists earlier conversations and opens one to carry on', async () => {
  renderAt('/chat');
  await screen.findByText('Said in last');
  fireEvent.click(screen.getByText('Earlier conversations (1)'));
  await act(async () => { fireEvent.click(screen.getByText('A quiet day at the allotment.')); });
  expect(await screen.findByText('Said in older')).toBeTruthy();
  expect(screen.getByTestId('where').textContent).toBe('?c=older');
});

it('starts a new conversation only on the click', async () => {
  calls.length = 0;
  renderAt('/chat');
  await screen.findByText('Said in last');
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'New conversation' })); });
  await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('?c=fresh'));
  expect(calls.filter(c => c === 'start')).toHaveLength(1);
});

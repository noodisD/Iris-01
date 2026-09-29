import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import type { DiscussionPreview, EvidenceRef } from '@/types/api';
import type * as ChatApi from '@/api/chat';

const server = vi.hoisted(() => ({ changed: false, fail: false, wait: null as Promise<void> | null,
  sent: [] as unknown[] }));
vi.mock('@/hooks/useData', () => ({ useUser: () => ({ data: null }) }));
vi.mock('@/hooks/useTalk', () => ({ useTalk: () => ({ end: () => {}, start: async () => {} }) }));
vi.mock('@/api/chat', async importOriginal => {
  const actual = await importOriginal<typeof ChatApi>();
  return {
    ...actual,
    startConversation: async () => ({ id: 'session', messageCount: 0 }),
    getMessages: async () => [],
    getDiscussionPreview: async (ref: EvidenceRef): Promise<DiscussionPreview> => ({
      ref: server.changed ? { ...ref, snapshot: 'b'.repeat(64) } : ref,
      title: 'A garden pattern', question: 'What made this different?',
      changed: server.changed && ref.snapshot !== 'b'.repeat(64),
      evidence: { pattern: { id: 'garden', name: 'A garden pattern' }, occasions: [{
        id: 'one', recordedOn: '2024-05-10', response: 'Replanted the bed', outcome: 'It grew',
        tone: 'better', ownerVerdict: null, citations: [{ entryId: '42', sourceType: 'reflection',
          text: 'Replanted the bed', entryDate: '2024-05-10' }],
      }] } as DiscussionPreview['evidence'],
    }),
    streamReply: async function* (_id: string, text: string, _voice: boolean, ref: EvidenceRef) {
      server.sent.push({ text, ref });
      if (server.wait) await server.wait;
      if (server.fail) { server.changed = true; throw new actual.ReplyFailed('Evidence changed', false); }
      yield { text: 'The account is one example.' };
      yield { text: '', done: true, messageId: 'saved' };
    },
  };
});
import { ChatScreen } from './ChatScreen';

const ref: EvidenceRef = { kind: 'pattern', patternId: 'garden', range: '90d', snapshot: 'a'.repeat(64) };
function JournalReturn() {
  const navigate = useNavigate();
  return <button onClick={() => navigate(-1)}>Return to chat</button>;
}

function show(withRef = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[
    withRef ? `/chat?evidence=${encodeURIComponent(JSON.stringify(ref))}` : '/chat',
  ]}><Routes><Route path="/chat" element={<ChatScreen />} />
    <Route path="/journal" element={<JournalReturn />} /></Routes></MemoryRouter></QueryClientProvider>);
}
beforeEach(() => { sessionStorage.clear(); server.changed = false; server.fail = false;
  server.wait = null; server.sent = []; });

it('previews located source, leaves the question editable, and sends only on demand', async () => {
  show();
  expect(await screen.findByRole('link', { name: 'Open entry' })).toHaveAttribute('href', '/journal?entry=42');
  expect(screen.getByRole('textbox', { name: 'Message to Iris' })).toHaveValue('What made this different?');
  expect(server.sent).toHaveLength(0);
  expect(screen.getByRole('button', { name: 'Talk' })).toBeDisabled();
  fireEvent.change(screen.getByRole('textbox', { name: 'Message to Iris' }),
    { target: { value: 'I actually waited a week.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  await waitFor(() => expect(server.sent).toEqual([{ text: 'I actually waited a week.', ref }]));
  expect(screen.getByRole('link', { name: 'Back to source' })).toHaveAttribute('href',
    '/patterns/garden?range=90d');
});

it('retains an edited unsent draft and selected range after following a citation and returning', async () => {
  show();
  fireEvent.change(await screen.findByRole('textbox', { name: 'Message to Iris' }),
    { target: { value: 'This part matters to me' } });
  fireEvent.click(screen.getByRole('link', { name: 'Open entry' }));
  fireEvent.click(screen.getByRole('button', { name: 'Return to chat' }));
  expect(await screen.findByRole('textbox', { name: 'Message to Iris' }))
    .toHaveValue('This part matters to me');
  expect(screen.getByRole('link', { name: 'Back to source' }))
    .toHaveAttribute('href', '/patterns/garden?range=90d');
  expect(server.sent).toHaveLength(0);
});

it('restores a failed unsaved draft and requires reviewing changed evidence', async () => {
  server.fail = true;
  show();
  await screen.findByRole('link', { name: 'Open entry' });
  fireEvent.change(screen.getByRole('textbox', { name: 'Message to Iris' }),
    { target: { value: 'Keep my words' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  await waitFor(() => expect(screen.getByRole('textbox', { name: 'Message to Iris' })).toHaveValue('Keep my words'));
  expect(await screen.findByRole('button', { name: 'Use updated evidence' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  server.fail = false;
  fireEvent.click(screen.getByRole('button', { name: 'Use updated evidence' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  await waitFor(() => expect(server.sent).toHaveLength(2));
  expect(server.sent[1]).toEqual({ text: 'Keep my words', ref: { ...ref, snapshot: 'b'.repeat(64) } });
});

it('keeps the next unsent draft when an earlier selected turn finishes', async () => {
  // ES2023 target has no Promise.withResolvers; hold the provider reply until the next draft is typed.
  let finish!: () => void;
  server.wait = new Promise<void>(resolve => { finish = resolve; });
  show();
  const composer = await screen.findByRole('textbox', { name: 'Message to Iris' });
  fireEvent.change(composer, { target: { value: 'First question' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  await waitFor(() => expect(server.sent).toHaveLength(1));
  fireEvent.change(composer, { target: { value: 'Next question' } });
  finish();
  await waitFor(() => expect(screen.getByText('The account is one example.')).toBeInTheDocument());
  fireEvent.click(screen.getByRole('link', { name: 'Open entry' }));
  fireEvent.click(screen.getByRole('button', { name: 'Return to chat' }));
  expect(await screen.findByRole('textbox', { name: 'Message to Iris' })).toHaveValue('Next question');
});

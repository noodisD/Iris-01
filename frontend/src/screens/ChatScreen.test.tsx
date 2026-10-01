import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import type { DiscussionPreview, EvidenceRef, PatternDetail } from '@/types/api';
import type * as ChatApi from '@/api/chat';

const server = vi.hoisted(() => ({ changed: false, fail: false, corrected: false,
  wait: null as Promise<void> | null, sent: [] as unknown[] }));
vi.mock('@/hooks/useData', () => ({ useUser: () => ({ data: null }) }));
vi.mock('@/hooks/useTalk', () => ({ useTalk: () => ({ end: () => {}, start: async () => {} }) }));
vi.mock('@/api/chat', async importOriginal => {
  const actual = await importOriginal<typeof ChatApi>();
  return {
    ...actual,
    startConversation: async () => ({ id: 'session', messageCount: 0 }),
    getMessages: async () => [],
    getDiscussionPreview: async (ref: EvidenceRef): Promise<DiscussionPreview> => {
      const dynamicId = `d_${'1'.repeat(64)}`;
      const snapshot = server.changed ? 'b'.repeat(64) : ref.snapshot;
      const coverage = { range: '90d' as const, asOf: '2024-05-10',
        recordedFrom: '2024-05-10', recordedTo: '2024-05-10',
        entryCount: 1, accountCount: 1, undatedAccountCount: 0 };
      const evidence: PatternDetail = {
        pattern: { id: dynamicId, title: 'A request dynamic',
          context: { text: 'When asked', refs: [{ accountId: 'one', field: 'situation', citationIndex: 0 }] },
          response: { text: 'I answered', refs: [{ accountId: 'one', field: 'response', citationIndex: 0 }] },
          evidenceState: 'owner_described', ownerMeanings: [], immediateReturn: null, laterCost: null,
          possibleMeaning: null, alternative: null, openQuestion: 'What made this different?',
          lensMatches: [], exceptionGroupIds: [], responseElsewhereGroupIds: [],
          independentGroupCount: 1, accountCount: 1, entryCount: 1, recordedFrom: '2024-05-10',
          recordedTo: '2024-05-10', undatedAccountCount: 0, exceptionCount: 0,
          unknownAccountCount: 0, example: null, range: '90d', asOf: '2024-05-10',
          claimHash: snapshot, snapshot, feedback: null },
        accounts: { one: { id: 'one', actor: 'self', recordedOn: '2024-05-10', recordKind: 'event',
          situation: 'Someone asked', response: 'Replanted the bed', selfReport: null, explanation: null,
          demand: null, information: null, feeling: null, concern: null, immediateOutcome: null,
          laterOutcome: null, domain: null, citations: [{ entryId: '42', sourceType: 'reflection',
            text: 'Replanted the bed', entryDate: '2024-05-10' }] } },
        memberships: { [dynamicId]: [{ dynamicId, accountId: 'one', groupId: 'group',
          role: 'support', contextDecision: 'present', responseDecision: 'present',
          relationDecision: 'linked', refs: [], ownerVerdict: null, verdictNote: null, excluded: false }] },
        groups: { [dynamicId]: [{ id: 'group', role: 'support', accountIds: ['one'],
          independentlyCountable: true, independenceUncertain: false }] },
        lenses: [], checks: { checked: 1, unclear: 0, omittedAccounts: 0,
          omittedFields: 0, exceptionSearchComplete: true }, coverage, snapshot,
        status: { stage: 'ready', readerVersion: snapshot, discoveryVersion: snapshot,
          interpretationVersion: snapshot, libraryVersion: snapshot, model: 'test-model',
          eligibleEntries: 1, currentEntries: 1, unreadEntries: 0, pendingEntries: 0,
          failedEntries: 0, excludedEntries: 0, omittedAccounts: 0, omittedFields: 0,
          synthesisPending: false, synthesisFailed: false, lastCompletedAt: null, estimate: {
            readingRequests: 0, synthesisRequests: 0, tokensIn: 0, tokensOut: 0,
            costText: 'zero', approximate: true } },
      };
      if (server.corrected) {
        evidence.accounts.two = { ...evidence.accounts.one, id: 'two',
          citations: [{ entryId: '43', sourceType: 'reflection',
            text: 'Rejected source passage', entryDate: '2024-05-09' }] };
        evidence.memberships[dynamicId].push({ ...evidence.memberships[dynamicId][0],
          accountId: 'two', groupId: 'corrected', ownerVerdict: 'no', excluded: true });
        evidence.groups[dynamicId].unshift({ id: 'corrected', role: 'unclear',
          accountIds: ['two'], independentlyCountable: false, independenceUncertain: false });
      }
      return { ref: server.changed ? { ...ref, snapshot } : ref,
        title: 'A request dynamic', question: 'What made this different?',
        changed: server.changed && ref.snapshot !== snapshot, evidence };
    },
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

const ref: EvidenceRef = { kind: 'dynamic', dynamicId: `d_${'1'.repeat(64)}`,
  range: '90d', snapshot: 'a'.repeat(64) };
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
  server.corrected = false; server.wait = null; server.sent = []; });

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
    `/patterns/${ref.kind === 'dynamic' ? ref.dynamicId : ''}?range=90d`);
});

it('keeps an owner-rejected passage out of the selected chat preview', async () => {
  server.corrected = true;
  show();
  expect(await screen.findByText(/1 checked groups/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Open entry' })).toHaveAttribute('href', '/journal?entry=42');
  expect(screen.queryByText('Rejected source passage')).not.toBeInTheDocument();
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
    .toHaveAttribute('href', `/patterns/${ref.kind === 'dynamic' ? ref.dynamicId : ''}?range=90d`);
  expect(server.sent).toHaveLength(0);
});

it('requires review when cited writing changes while the unsent draft is away in Journal', async () => {
  show();
  fireEvent.change(await screen.findByRole('textbox', { name: 'Message to Iris' }),
    { target: { value: 'Keep the original question' } });
  fireEvent.click(screen.getByRole('link', { name: 'Open entry' }));
  server.changed = true;
  fireEvent.click(screen.getByRole('button', { name: 'Return to chat' }));
  expect(await screen.findByRole('button', { name: 'Use updated evidence' })).toBeInTheDocument();
  expect(screen.getByRole('textbox', { name: 'Message to Iris' })).toHaveValue('Keep the original question');
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
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

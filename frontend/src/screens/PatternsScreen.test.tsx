import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import type { PatternDetail, PersonalAccount, PersonalPattern } from '@/types/api';

const id = `d_${'1'.repeat(64)}`;
const snapshot = 'a'.repeat(64);
const coverage = { range: 'all' as const, asOf: '2026-10-01', recordedFrom: '2026-09-19',
  recordedTo: '2026-09-20', entryCount: 2, accountCount: 2, undatedAccountCount: 0 };
const status = { readerVersion: snapshot, discoveryVersion: snapshot, interpretationVersion: snapshot,
  libraryVersion: snapshot, model: 'test-model', stage: 'ready' as const, eligibleEntries: 2,
  currentEntries: 2, unreadEntries: 0, pendingEntries: 0, failedEntries: 0, excludedEntries: 0,
  omittedAccounts: 0, omittedFields: 0, synthesisPending: false, synthesisFailed: false,
  lastCompletedAt: null, estimate: { readingRequests: 0, synthesisRequests: 0,
    tokensIn: 0, tokensOut: 0, costText: 'zero', approximate: true as const } };
const citation = { entryId: '42', sourceType: 'reflection', entryDate: '2026-09-20',
  text: 'When she asked, I said yes right away.' };
const account: PersonalAccount = { id: 'a', actor: 'self', recordKind: 'event',
  situation: 'When she asked', response: 'I said yes right away', demand: null, information: null,
  feeling: null, concern: null, immediateOutcome: null, laterOutcome: null, explanation: null,
  selfReport: null, domain: null, recordedOn: '2026-09-20', citations: [citation] };
const another: PersonalAccount = { ...account, id: 'b', recordedOn: '2026-09-19',
  citations: [{ entryId: '43', sourceType: 'reflection', entryDate: '2026-09-19',
    text: 'When my colleague asked, I agreed quickly.' }] };
const clause = { text: 'I said yes when she asked', refs: [{ accountId: 'a', field: 'response', citationIndex: 0 }] };
const pattern: PersonalPattern = { id, title: 'Saying yes when asked', context: clause,
  response: clause, evidenceState: 'emerging', ownerMeanings: [], immediateReturn: null,
  laterCost: null, possibleMeaning: null, alternative: null, openQuestion: 'What differed?',
  lensMatches: [], exceptionGroupIds: [], responseElsewhereGroupIds: [], independentGroupCount: 2,
  accountCount: 2, entryCount: 2, recordedFrom: '2026-09-19', recordedTo: '2026-09-20',
  undatedAccountCount: 0, exceptionCount: 0, unknownAccountCount: 0,
  example: { accountId: 'a', recordedOn: '2026-09-20', citation }, range: 'all', asOf: '2026-10-01',
  claimHash: snapshot, snapshot, feedback: { verdict: null, note: 'A saved thought',
    needsReview: true, updatedAt: '2026-09-21T10:00:00Z' } };
const membership = { dynamicId: id, accountId: 'a', groupId: 'a', role: 'support' as const,
  contextDecision: 'present' as const, responseDecision: 'present' as const,
  relationDecision: 'linked' as const, refs: [], ownerVerdict: null, verdictNote: 'My source note', excluded: false };
const detail: PatternDetail = { pattern, accounts: { a: account, b: another },
  memberships: { [id]: [membership, { ...membership, accountId: 'b', groupId: 'b', verdictNote: null }] },
  groups: { [id]: [
    { id: 'a', accountIds: ['a'], role: 'support', independentlyCountable: true, independenceUncertain: false },
    { id: 'b', accountIds: ['b'], role: 'support', independentlyCountable: true, independenceUncertain: false },
  ] }, lenses: [],
  checks: { checked: 2, unclear: 0, omittedAccounts: 0, omittedFields: 0,
    exceptionSearchComplete: true },
  coverage, status, snapshot };
const sent = vi.hoisted(() => ({ accounts: [] as unknown[], patterns: [] as unknown[],
  invalidateOnAccountSave: false, interpreting: false }));
vi.mock('@/api/patterns', () => ({
  getPatterns: async () => ({ patterns: [pattern], coverage, status, snapshot }),
  getPattern: async () => {
    if (sent.interpreting) throw new Error('corrected evidence not current');
    return detail;
  },
  setAccountVerdict: async (_id: string, accountId: string, feedback: unknown) => {
    sent.accounts.push({ accountId, feedback });
    if (sent.invalidateOnAccountSave) sent.interpreting = true;
    return { ok: true };
  },
  setPatternVerdict: async (_id: string, feedback: unknown) => {
    sent.patterns.push(feedback); return { feedback: null, snapshot };
  },
  getDiscoveryStatus: async () => sent.interpreting
    ? { ...status, stage: 'interpreting' as const, synthesisPending: true } : status,
  refreshDiscovery: async () => ({ queuedEntries: 0, queuedSynthesis: false }),
}));
import { PatternsScreen } from './PatternsScreen';

function show(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/patterns" element={<PatternsScreen />} />
    <Route path="/patterns/:id" element={<PatternsScreen />} />
  </Routes></MemoryRouter></QueryClientProvider>);
}
beforeEach(() => {
  sent.accounts = []; sent.patterns = [];
  sent.invalidateOnAccountSave = false; sent.interpreting = false;
});

it('shows the personal observation and its typed discussion link without a top-level library card', async () => {
  show('/patterns?range=90d');
  const card = await screen.findByRole('article');
  expect(within(card).getByText('I said yes when she asked → I said yes when she asked')).toBeInTheDocument();
  expect(within(card).getByText(/at least 2 distinct occasions identified/)).toBeInTheDocument();
  expect(within(card).getByRole('link', { name: 'Open entry' })).toHaveAttribute('href', '/journal?entry=42');
  const href = within(card).getByRole('link', { name: 'Explore with Iris' }).getAttribute('href')!;
  expect(JSON.parse(new URL(href, 'http://localhost').searchParams.get('evidence')!))
    .toEqual({ kind: 'dynamic', dynamicId: id, range: '90d', snapshot });
});

it('keeps absent results absent and exposes the full checked group and corrections', async () => {
  show(`/patterns/${id}`);
  expect(await screen.findByText(/Immediate return:/)).toBeInTheDocument();
  expect(screen.getAllByText('Not recorded').length).toBeGreaterThan(0);
  const group = screen.getByRole('region', { name: 'Event group a' });
  expect(within(group).getByRole('link', { name: 'Open entry' })).toHaveAttribute('href', '/journal?entry=42');
  expect(screen.getByText(/saved opinion needs review/i)).toBeInTheDocument();
});

it('saves an account verdict with its note in one revision-checked correction', async () => {
  show(`/patterns/${id}`);
  const group = await screen.findByRole('region', { name: 'Event group a' });
  fireEvent.click(within(group).getByRole('radio', { name: 'Not this' }));
  fireEvent.change(within(group).getByRole('textbox', { name: 'Note about this account' }),
    { target: { value: 'This was a different occasion.' } });
  expect(sent.accounts).toEqual([]);
  fireEvent.click(within(group).getByRole('button', { name: 'Save correction' }));
  await waitFor(() => expect(sent.accounts).toEqual([{ accountId: 'a',
    feedback: { range: 'all', snapshot, verdict: 'no', note: 'This was a different occasion.' } }]));
  fireEvent.click(screen.getByRole('radio', { name: "Doesn't ring true" }));
  await waitFor(() => expect(sent.patterns).toContainEqual({ range: 'all', snapshot,
    verdict: 'does_not', note: 'A saved thought' }));
});

it('reports rechecking instead of a generic load error while a correction invalidates the view', async () => {
  sent.invalidateOnAccountSave = true;
  show(`/patterns/${id}`);
  const group = await screen.findByRole('region', { name: 'Event group a' });
  fireEvent.click(within(group).getByRole('radio', { name: 'Not this' }));
  fireEvent.click(within(group).getByRole('button', { name: 'Save correction' }));
  expect(await screen.findByText(/corrected evidence is being rechecked/)).toBeInTheDocument();
  expect(screen.queryByText("Something didn't load.")).not.toBeInTheDocument();
});

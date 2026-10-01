import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import type { DayDifference, PersonalInsight, PersonalAccount } from '@/types/api';

const state = vi.hoisted(() => ({
  writing: { data: undefined as unknown, isPending: false, isError: false, refetch: vi.fn() },
  days: { data: undefined as unknown, isPending: false, isError: false, refetch: vi.fn() },
  detail: { data: undefined as unknown, isPending: false, isError: false, refetch: vi.fn() },
  mutate: vi.fn(),
}));
const hash = 'a'.repeat(64);
const dynamicId = `d_${'1'.repeat(64)}`;
const insightId = `i_${'2'.repeat(64)}`;
const status = { readerVersion: hash, discoveryVersion: hash, interpretationVersion: hash,
  libraryVersion: hash, model: 'test', stage: 'ready', eligibleEntries: 1, currentEntries: 1,
  unreadEntries: 0, pendingEntries: 0, failedEntries: 0, excludedEntries: 0, omittedAccounts: 0,
  omittedFields: 0, synthesisPending: false, synthesisFailed: false, lastCompletedAt: null,
  estimate: { readingRequests: 0, synthesisRequests: 0, tokensIn: 0, tokensOut: 0,
    costText: 'zero', approximate: true } };
vi.mock('@/hooks/usePatterns', () => ({
  usePersonalInsights: () => state.writing,
  usePersonalInsight: () => state.detail,
  useInsightVerdict: () => ({ mutate: state.mutate, isPending: false, isError: false }),
  useDayDifferences: () => state.days,
  useDayDifferenceDetail: () => state.detail,
  useDayDifferenceVerdict: () => ({ mutate: state.mutate, isPending: false, isError: false }),
  useDiscoveryStatus: () => ({ data: status, isPending: false, isError: false }),
  useDiscoveryRefresh: () => ({ mutate: state.mutate, isPending: false, isError: false }),
}));
import { InsightsScreen } from './InsightsScreen';

const coverage = { range: 'all' as const, asOf: '2026-10-01', recordedFrom: '2026-09-10',
  recordedTo: '2026-09-20', accountCount: 4, entryCount: 4, undatedAccountCount: 0 };
const diagnostics = { measuredDays: 10, checkinDays: 10, overlappingDays: 10,
  eligibleComparisons: 1, reason: null };
const measured: DayDifference = {
  outcome: 'energy', split: 'office_home', sentence: '', leftCount: 12, rightCount: 9,
  leftMean: 4.1, rightMean: 6.3, pValue: 0.005, verdict: null, leftLabel: 'office days',
  rightLabel: 'home days', threshold: null, snapshot: hash,
  coverage: { range: 'all', asOf: '2026-10-01', recordedFrom: '2026-09-10',
    recordedTo: '2026-09-20', measuredDays: 21, checkinDays: 21, overlappingDays: 21 },
};
const clause = { text: 'I responded after a request', refs: [{ accountId: 'a', field: 'response', citationIndex: 0 }] };
const hypothesis = { text: 'It may have kept the exchange easy.', premises: [clause],
  scopeGroupIds: ['g1'], ownerReportIds: [] };
const insight: PersonalInsight = { id: insightId, kind: 'contextual_difference', dynamicIds: [dynamicId],
  title: 'A different response to a request', observation: clause, possibleMeaning: hypothesis,
  alternative: { ...hypothesis, text: 'It may reflect the available time.' },
  immediateReturn: null, laterCost: null, supportingGroups: ['g1'], contraryGroups: ['g2'],
  unknownAccountIds: ['c'], question: 'What distinguished these occasions?',
  leftLabel: 'Agreed', rightLabel: 'Paused', leftGroupIds: ['g1'], rightGroupIds: ['g2'],
  range: 'all', asOf: '2026-10-01', claimHash: hash, snapshot: hash,
  feedback: { verdict: null, note: 'Keep this exact note', needsReview: false,
    updatedAt: '2026-09-22T10:00:00Z' } };
const accounts: Record<string, PersonalAccount> = Object.fromEntries(['a', 'b', 'c'].map((id, index) => [id, {
  id, actor: 'self', recordKind: 'event', situation: `A request ${id}`,
  response: `I responded ${id}`, demand: null, information: null, feeling: null,
  concern: null, immediateOutcome: null, laterOutcome: null, explanation: null,
  selfReport: null, domain: null, recordedOn: '2026-09-20',
  citations: [{ entryId: String(41 + index), sourceType: 'reflection', entryDate: '2026-09-20',
    text: `A request ${id}; I responded ${id}` }],
}]));

beforeEach(() => {
  state.writing = { data: { insights: [insight], coverage, status, snapshot: hash },
    isPending: false, isError: false, refetch: vi.fn() };
  state.days = { data: { differences: [], diagnostics }, isPending: false, isError: false, refetch: vi.fn() };
  state.detail = { data: { insight, accounts, memberships: { [dynamicId]: [] }, groups: {
    [dynamicId]: [
      { id: 'g1', accountIds: ['a'], role: 'support', independentlyCountable: true, independenceUncertain: false },
      { id: 'g2', accountIds: ['b'], role: 'exception', independentlyCountable: true, independenceUncertain: false },
    ] }, coverage, status, snapshot: hash }, isPending: false, isError: false, refetch: vi.fn() };
  state.mutate.mockClear();
});

it('keeps measured-day differences available when writing fails', () => {
  state.days.data = { differences: [measured], diagnostics };
  state.writing.isError = true;
  render(<MemoryRouter><InsightsScreen /></MemoryRouter>);
  const days = screen.getByRole('region', { name: 'Measured day differences' });
  expect(within(days).getByRole('article', { name: 'energy by office home' }))
    .toHaveTextContent('energy — office days: 4.1 across 12 days');
  fireEvent.click(within(screen.getByRole('region', { name: 'Personal insights' }))
    .getByRole('button', { name: 'Try again' }));
  expect(state.writing.refetch).toHaveBeenCalledOnce();
});

it('separates tentative interpretation from observation and retains exact note when judged', () => {
  render(<MemoryRouter><InsightsScreen /></MemoryRouter>);
  const card = screen.getByRole('article', { name: insight.title });
  expect(within(card).getByRole('region', { name: 'Tentative explanation' }))
    .toHaveTextContent('It may reflect the available time.');
  fireEvent.click(within(card).getByRole('radio', { name: 'Rings true' }));
  expect(state.mutate.mock.calls[0][0]).toEqual({ range: 'all', snapshot: hash,
    verdict: 'rings_true', note: 'Keep this exact note' });
});

it('exposes supporting, contrary, unknown, and every original entry without truncation', () => {
  render(<MemoryRouter><InsightsScreen /></MemoryRouter>);
  fireEvent.click(screen.getByRole('button', { name: 'See all evidence' }));
  expect(screen.getByRole('region', { name: 'Supporting event groups' })).toHaveTextContent('I responded a');
  expect(screen.getByRole('region', { name: 'Contrary event groups' })).toHaveTextContent('I responded b');
  expect(screen.getByRole('region', { name: 'Unknown accounts' })).toHaveTextContent('I responded c');
  expect(new Set(screen.getAllByRole('link', { name: 'Open entry' }).map(link => link.getAttribute('href'))))
    .toEqual(new Set(['/journal?entry=41', '/journal?entry=42', '/journal?entry=43']));
});

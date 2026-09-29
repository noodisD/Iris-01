import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DayDifference, Difference } from '@/types/api';

const state = vi.hoisted(() => ({
  writing: { data: undefined as unknown, isPending: false, isError: false, refetch: vi.fn() },
  days: { data: undefined as unknown, isPending: false, isError: false, refetch: vi.fn() },
  detail: { data: undefined as unknown, isPending: false, isError: false, refetch: vi.fn() },
  mutate: vi.fn(),
}));

vi.mock('@/hooks/usePatterns', () => ({
  useDifferences: () => state.writing,
  useDifferenceDetail: () => state.detail,
  useDifferenceVerdict: () => ({ mutate: state.mutate, isPending: false, isError: false }),
  usePatternVerdict: () => ({ mutate: state.mutate, isPending: false, isError: false }),
  useDayDifferences: () => state.days,
  useDayDifferenceDetail: () => state.detail,
  useDayDifferenceVerdict: () => ({ mutate: state.mutate, isPending: false, isError: false }),
  useDiscoveryStatus: () => ({ data: {
    eligibleEntries: 1, currentEntries: 1, unreadEntries: 0, pendingEntries: 0, failedEntries: 0,
    excludedEntries: 0, omittedAccounts: 0, lastCompletedAt: null, model: 'test-model',
    estimatedRequests: 0, estimate: 'Approximate: no unread entries',
  }, isPending: false, isError: false }),
  useDiscoveryRefresh: () => ({ mutate: state.mutate, isPending: false, isError: false }),
}));

import { InsightsScreen } from './InsightsScreen';

const coverage = { range: 'all' as const, asOf: '2026-09-29', recordedFrom: '2026-09-10',
  recordedTo: '2026-09-20', accountCount: 13, entryCount: 13, undatedAccountCount: 0 };
const diagnostics = { measuredDays: 10, checkinDays: 10, overlappingDays: 10,
  eligibleComparisons: 1, reason: null };

function diff(patternId: string, otherId: string, verdict: Difference['verdict'] = null): Difference {
  return { patternId, patternName: `Pattern ${patternId}`, otherId, otherName: `Pattern ${otherId}`,
    worse: 5, worseTotal: 6, better: 1, betterTotal: 7, verdict, patternVerdict: null,
    worseRate: 5 / 6, betterRate: 1 / 7, rateGap: 5 / 6 - 1 / 7,
    coverage, snapshot: 'a'.repeat(64), sampleLabel: 'exploratory', dismissed: false };
}

const measured: DayDifference = {
  outcome: 'energy', split: 'office_home', sentence: '',
  leftCount: 12, rightCount: 9, leftMean: 4.1, rightMean: 6.3, pValue: 0.005, verdict: null,
  leftLabel: 'office days', rightLabel: 'home days', threshold: null, snapshot: 'b'.repeat(64),
  coverage: { range: 'all', asOf: '2026-09-29', recordedFrom: '2026-09-10',
    recordedTo: '2026-09-20', measuredDays: 21, checkinDays: 21, overlappingDays: 21 },
};

function show(differences: Difference[]) {
  state.writing = { ...state.writing, data: { differences, reflections: [], coverage } };
  render(<MemoryRouter><InsightsScreen /></MemoryRouter>);
}

beforeEach(() => {
  state.writing = { data: undefined, isPending: false, isError: false, refetch: vi.fn() };
  state.days = { data: { differences: [], diagnostics }, isPending: false, isError: false, refetch: vi.fn() };
  state.detail = { data: undefined, isPending: false, isError: false, refetch: vi.fn() };
  state.mutate.mockClear();
});

describe('Insights', () => {
  it('keeps measured evidence and its actions available when writing fails', () => {
    state.days.data = { differences: [measured], diagnostics };
    state.writing.isError = true;
    render(<MemoryRouter><InsightsScreen /></MemoryRouter>);
    const days = screen.getByRole('region', { name: 'Days compared' });
    expect(within(days).getByRole('article', { name: 'energy by office home' }))
      .toHaveTextContent('energy — office days: 4.1 across 12 days');
    fireEvent.click(within(screen.getByRole('region', { name: 'Writing differences' }))
      .getByRole('button', { name: 'Try again' }));
    expect(state.writing.refetch).toHaveBeenCalledOnce();
  });

  it('keeps writing feedback available when measured days fail', () => {
    state.days.isError = true;
    show([diff('a', 'b')]);
    const writing = screen.getByRole('region', { name: 'Writing differences' });
    expect(within(writing).getByText(/Read as worse:/)).toHaveTextContent('5/6 (83%)');
    expect(within(writing).getByRole('radio', { name: 'Rings true' })).toBeEnabled();
    fireEvent.click(within(screen.getByRole('region', { name: 'Days compared' }))
      .getByRole('button', { name: 'Try again' }));
    expect(state.days.refetch).toHaveBeenCalledOnce();
  });

  it('does not promote note-only feedback to a saved judgment and retains its note', () => {
    show([diff('a', 'b', { verdict: 'rings_true', note: null }),
      diff('c', 'd', { verdict: null, note: 'Look again at the grouping' })]);
    fireEvent.click(screen.getByRole('button', { name: 'Saved opinions' }));
    expect(screen.queryByRole('article', { name: 'Pattern c and Pattern d' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Current' }));
    const card = screen.getByRole('article', { name: 'Pattern c and Pattern d' });
    fireEvent.click(within(card).getByRole('radio', { name: 'Rings true' }));
    expect(state.mutate).toHaveBeenCalledWith({
      patternId: 'c', otherId: 'd', feedback: { verdict: 'rings_true', note: 'Look again at the grouping' },
    });
  });

  it('keeps every denominator member inspectable, not just the headline fraction', () => {
    const d = diff('a', 'b');
    const account = (id: string) => ({ id, recordedOn: '2026-09-20', domain: null,
      situation: 'I considered my options', response: `I chose option ${id}`, outcome: 'We talked',
      explanation: null, citations: [{ sourceType: 'reflection', entryId: id,
        entryDate: '2026-09-20', text: `I chose option ${id}` }],
      suggestedTone: 'better', ownerTone: null, tone: 'better',
      size: null, labelledBy: 'reader', ownerVerdict: null, verdictNote: null });
    state.detail.data = { difference: d, groups: {
      betterWith: [account('1'), account('2'), account('3'), account('4'), account('5'), account('6')],
      betterWithout: [], worseWith: [], worseWithout: [],
    }, mixedExcluded: 0 };
    show([d]);
    fireEvent.click(screen.getByRole('button', { name: 'See the evidence' }));
    expect(screen.getAllByRole('link', { name: 'Open entry' })).toHaveLength(5);
    fireEvent.click(screen.getByRole('button', { name: 'Show more' }));
    expect(screen.getAllByRole('link', { name: 'Open entry' })).toHaveLength(6);
  });
});

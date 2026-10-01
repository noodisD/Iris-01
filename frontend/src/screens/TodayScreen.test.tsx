import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import type { PersonalPattern } from '@/types/api';

const state = vi.hoisted(() => ({
  patterns: { data: undefined as unknown, isLoading: false, isError: false, refetch: vi.fn() },
  habits: { data: undefined as unknown, isLoading: false, isError: false, refetch: vi.fn() },
  verdict: vi.fn(),
}));
vi.mock('@/hooks/usePatterns', () => ({
  usePatterns: () => state.patterns,
  usePatternVerdict: () => ({ mutate: state.verdict, isPending: false, isError: false }),
}));
vi.mock('@/hooks/useHabits', () => ({ useHabits: () => state.habits }));
import { TodayScreen, nextPattern } from './TodayScreen';

const hash = 'a'.repeat(64);
function pattern(id: string, feedback: PersonalPattern['feedback'] = null): PersonalPattern {
  const clause = { text: 'When asked, I paused', refs: [] };
  return { id, title: `Pattern ${id}`, context: clause, response: clause,
    evidenceState: 'emerging', ownerMeanings: [], immediateReturn: null, laterCost: null,
    possibleMeaning: null, alternative: null, openQuestion: 'What differed?', lensMatches: [],
    exceptionGroupIds: [], responseElsewhereGroupIds: [], independentGroupCount: 2,
    accountCount: 2, entryCount: 2, recordedFrom: '2026-09-01', recordedTo: '2026-09-02',
    undatedAccountCount: 0, exceptionCount: 0, unknownAccountCount: 0, example: null,
    range: 'all', asOf: '2026-10-01', claimHash: hash, snapshot: hash, feedback };
}
const feedback = (verdict: 'rings_true' | 'does_not' | null, note: string | null, needsReview = false) =>
  ({ verdict, note, needsReview, updatedAt: '2026-09-22T10:00:00Z' });
beforeEach(() => {
  state.patterns = { data: { patterns: [], status: { stage: 'ready' } },
    isLoading: false, isError: false, refetch: vi.fn() };
  state.habits = { data: { habits: [], doneCount: 0, totalCount: 0 },
    isLoading: false, isError: false, refetch: vi.fn() };
  state.verdict.mockClear();
});

it('uses checked list order, not library frequency; a note-only row stays reviewable', () => {
  const first = pattern('first', feedback('rings_true', null));
  const noted = pattern('noted', feedback(null, 'Keep these words'));
  state.patterns.data = { patterns: [first, noted, pattern('later')], status: { stage: 'ready' } };
  render(<MemoryRouter><TodayScreen /></MemoryRouter>);
  expect(screen.getByRole('heading', { name: 'Pattern noted' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('radio', { name: 'Rings true' }));
  expect(state.verdict).toHaveBeenCalledWith({ range: 'all', snapshot: hash,
    verdict: 'rings_true', note: 'Keep these words' });
});

it('makes stale saved feedback reviewable but does not feature unavailable synthesis', () => {
  expect(nextPattern([pattern('review', feedback('rings_true', 'Old', true))])?.id).toBe('review');
  state.patterns.data = { patterns: [pattern('review')], status: { stage: 'checking' } };
  render(<MemoryRouter><TodayScreen /></MemoryRouter>);
  expect(screen.queryByRole('heading', { name: 'Pattern review' })).toBeNull();
});

it('reports an unavailable pattern request independently of habits', () => {
  state.patterns.isError = true;
  render(<MemoryRouter><TodayScreen /></MemoryRouter>);
  expect(screen.getByRole('alert')).toHaveTextContent("Patterns didn't load.");
});

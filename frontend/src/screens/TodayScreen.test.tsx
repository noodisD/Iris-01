/**
 * Today offers the pattern most worth a verdict, as a question, and a failed
 * load says so instead of showing an empty page.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { PatternSummary } from '@/types/api';

const state = vi.hoisted(() => ({
  patterns: { data: undefined as unknown, isLoading: false, isError: false, refetch: () => {} },
  habits: { data: undefined as unknown, isLoading: false, isError: false, refetch: () => {} },
  verdict: vi.fn(),
}));

vi.mock('@/hooks/usePatterns', () => ({
  usePatterns: () => state.patterns,
  usePatternVerdict: () => ({ mutate: state.verdict, isPending: false }),
}));
vi.mock('@/hooks/useHabits', () => ({ useHabits: () => state.habits }));

import { TodayScreen, nextPattern } from './TodayScreen';

function pattern(id: string, occasions: number, verdict: PatternSummary['verdict'] = null): PatternSummary {
  return {
    id, name: `Pattern ${id}`, statement: `What ${id} says.`, holdsWhen: [], notWhen: [], question: '',
    basis: null, evidence: null, source: null, occasions, tones: { better: 0, worse: occasions, mixed: 0 },
    entryCount: occasions, recordedFrom: occasions ? '2026-09-01' : null,
    recordedTo: occasions ? '2026-09-01' : null, undatedAccountCount: 0,
    examples: [], snapshot: 'a'.repeat(64),
    coverage: { range: 'all', asOf: '2026-09-29', recordedFrom: occasions ? '2026-09-01' : null,
      recordedTo: occasions ? '2026-09-01' : null, entryCount: occasions, accountCount: occasions,
      undatedAccountCount: 0 },
    reviewed: 0, rejected: 0, labelledBy: [], verdict,
  };
}
const noHabits = { habits: [], doneCount: 0, totalCount: 0 };

function show() {
  render(<MemoryRouter><TodayScreen /></MemoryRouter>);
}

describe('Today', () => {
  it('offers the most frequent pattern still waiting for a verdict', () => {
    state.patterns = { ...state.patterns, isError: false, data: { patterns: [
      pattern('a', 9, { verdict: 'rings_true', note: null }), pattern('b', 4), pattern('c', 6), pattern('d', 0),
    ] } };
    state.habits = { ...state.habits, data: noHabits, isError: false };
    show();
    expect(screen.getByRole('heading', { name: 'Pattern c' })).toBeInTheDocument();
    expect(screen.getByText('6 recorded accounts in your writing')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: 'Rings true' }));
    expect(state.verdict).toHaveBeenCalledWith({ verdict: 'rings_true', note: null });
  });

  it('shows nothing when every found pattern has a verdict', () => {
    expect(nextPattern([pattern('a', 3, { verdict: 'does_not', note: null }), pattern('b', 0)])).toBeUndefined();
  });

  it('keeps a note-only pattern selectable and preserves its note on a quick verdict', () => {
    const noted = pattern('noted', 2, { verdict: null, note: 'Still considering it' });
    expect(nextPattern([noted])?.id).toBe('noted');
    state.patterns = { ...state.patterns, data: { patterns: [noted] }, isError: false };
    state.habits = { ...state.habits, data: noHabits, isError: false };
    show();
    fireEvent.click(screen.getByRole('radio', { name: 'Rings true' }));
    expect(state.verdict).toHaveBeenCalledWith({ verdict: 'rings_true', note: 'Still considering it' });
  });

  it('says when patterns did not load', () => {
    state.patterns = { ...state.patterns, data: undefined, isError: true };
    state.habits = { ...state.habits, data: noHabits, isError: false };
    show();
    expect(screen.getByRole('alert')).toHaveTextContent("Patterns didn't load.");
  });

  it('says when nothing loaded at all', () => {
    state.patterns = { ...state.patterns, data: undefined, isError: true };
    state.habits = { ...state.habits, data: undefined, isError: true };
    show();
    expect(screen.getByText("Something didn't load.")).toBeInTheDocument();
  });
});

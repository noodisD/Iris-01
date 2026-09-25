/**
 * Today offers the pattern most worth a verdict, as a question, and a failed
 * load says so instead of showing an empty page.
 */
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { PatternSummary } from '@/types/api';

const state = vi.hoisted(() => ({
  patterns: { data: undefined as unknown, isLoading: false, isError: false, refetch: () => {} },
  habits: { data: undefined as unknown, isLoading: false, isError: false, refetch: () => {} },
}));

vi.mock('@/hooks/usePatterns', () => ({ usePatterns: () => state.patterns }));
vi.mock('@/hooks/useHabits', () => ({ useHabits: () => state.habits }));

import { TodayScreen, nextPattern } from './TodayScreen';

function pattern(id: string, occasions: number, verdict: PatternSummary['verdict'] = null): PatternSummary {
  return {
    id, name: `Pattern ${id}`, statement: `What ${id} says.`, holdsWhen: [], notWhen: [], question: '',
    basis: null, evidence: null, source: null, occasions, tones: { better: 0, worse: occasions, mixed: 0 },
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
    expect(screen.getByText('Pattern c')).toBeInTheDocument();
    expect(screen.getByText(/6 occasions in your writing · does it ring true\?/)).toBeInTheDocument();
  });

  it('shows nothing when every found pattern has a verdict', () => {
    expect(nextPattern([pattern('a', 3, { verdict: 'does_not', note: null }), pattern('b', 0)])).toBeUndefined();
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

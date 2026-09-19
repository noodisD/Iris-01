/**
 * Today names the measurement it features, never a time the finding does not
 * have, and a failed load says so instead of showing an empty page.
 *
 * The kicker used to read "iris, just now" above a count that could span two
 * years, and a failed request left the screen silently blank.
 */
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  insights: { data: undefined as unknown, isLoading: false, isError: false, refetch: () => {} },
  habits: { data: undefined as unknown, isLoading: false, isError: false, refetch: () => {} },
}));

vi.mock('@/hooks/useInsights', () => ({ useInsights: () => state.insights }));
vi.mock('@/hooks/useHabits', () => ({ useHabits: () => state.habits }));

import { TodayScreen } from './TodayScreen';

const lifelong = {
  id: 'lifelong:7', kind: 'across the record', status: 'new', featured: true,
  headline: { line1: 'a', line2: 'b', line3: 'c' }, summary: 'Recurred 40 times across two years.',
  accentColor: 'sage', tags: [], confidence: 'medium', detectedAt: '2026-09-19T10:00:00Z', seen: false,
};
const noHabits = { habits: [], doneCount: 0, totalCount: 0 };

function show() {
  render(<MemoryRouter><TodayScreen /></MemoryRouter>);
}

describe('Today', () => {
  it('names the measurement, not "just now"', () => {
    state.insights = { ...state.insights, data: [lifelong], isError: false };
    state.habits = { ...state.habits, data: noHabits, isError: false };
    show();
    expect(screen.getByText('iris · across the record')).toBeInTheDocument();
    expect(screen.queryByText(/just now/)).toBeNull();
  });

  it('says when findings did not load', () => {
    state.insights = { ...state.insights, data: undefined, isError: true };
    state.habits = { ...state.habits, data: noHabits, isError: false };
    show();
    expect(screen.getByRole('alert')).toHaveTextContent("Findings didn't load.");
  });

  it('says when nothing loaded at all', () => {
    state.insights = { ...state.insights, data: undefined, isError: true };
    state.habits = { ...state.habits, data: undefined, isError: true };
    show();
    expect(screen.getByText("Something didn't load.")).toBeInTheDocument();
  });
});

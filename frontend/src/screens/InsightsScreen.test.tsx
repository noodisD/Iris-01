import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DayDifference, Difference } from '@/types/api';

const state = vi.hoisted(() => ({
  differences: { data: undefined as unknown, isPending: false, isError: false, refetch: () => {} },
  days: { data: undefined as unknown, isPending: false, isError: false, refetch: () => {} },
  mutate: vi.fn(),
}));

vi.mock('@/hooks/usePatterns', () => ({
  useDifferences: () => state.differences,
  useDifferenceVerdict: () => ({ mutate: state.mutate, isPending: false }),
  useDayDifferences: () => state.days,
  useDayDifferenceVerdict: () => ({ mutate: state.mutate, isPending: false, isError: false }),
}));

import { InsightsScreen } from './InsightsScreen';

function diff(patternId: string, otherId: string, verdict: Difference['verdict'] = null): Difference {
  return { patternId, patternName: `Pattern ${patternId}`, otherId, otherName: `Pattern ${otherId}`,
           worse: 5, worseTotal: 6, better: 1, betterTotal: 7, verdict, patternVerdict: null };
}

function show(differences: Difference[]) {
  state.differences = { ...state.differences, data: { differences } };
  render(<MemoryRouter><InsightsScreen /></MemoryRouter>);
}

const measuredDay: DayDifference = {
  outcome: 'energy', split: 'office_home',
  sentence: 'Energy averaged 4.1 on office days (12 days) and 6.3 on home days (9 days).',
  leftCount: 12, rightCount: 9, leftMean: 4.1, rightMean: 6.3, pValue: 0.005, verdict: null,
};

beforeEach(() => {
  state.differences = { data: undefined, isPending: false, isError: false, refetch: vi.fn() };
  state.days = { data: { differences: [] }, isPending: false, isError: false, refetch: vi.fn() };
  state.mutate.mockClear();
});

describe('Insights', () => {
  it('keeps measured comparisons visible when writing-derived differences fail', () => {
    state.days.data = { differences: [measuredDay] };
    state.differences.isError = true;
    render(<MemoryRouter><InsightsScreen /></MemoryRouter>);
    const days = screen.getByRole('region', { name: 'Days compared' });
    expect(within(days).getByRole('article', { name: 'energy by office home' })).toBeInTheDocument();
    expect(within(days).getByText('compared · 12 days / 9 days')).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole('region', { name: 'Writing differences' })).getByRole('button', { name: 'Try again' }));
    expect(state.differences.refetch).toHaveBeenCalledOnce();
  });

  it('keeps writing-derived differences usable when measured comparisons fail', () => {
    state.days.isError = true;
    show([diff('a', 'b')]);
    const writing = screen.getByRole('region', { name: 'Writing differences' });
    expect(within(writing).getByRole('article', { name: 'Pattern a and Pattern b' })).toBeInTheDocument();
    expect(within(writing).getByRole('button', { name: 'rings true' })).toBeEnabled();
    fireEvent.click(within(screen.getByRole('region', { name: 'Days compared' })).getByRole('button', { name: 'Try again' }));
    expect(state.days.refetch).toHaveBeenCalledOnce();
  });

  it('puts the ones waiting for a verdict first', () => {
    show([diff('a', 'b', { verdict: 'rings_true', note: null }), diff('c', 'd')]);
    const cards = screen.getAllByRole('article');
    expect(cards[0]).toHaveAccessibleName('Pattern c and Pattern d');
  });

});

/**
 * Insights are differences in outcome, read as a sentence with both sides'
 * counts, and the ones still waiting for a verdict come first.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { Difference } from '@/types/api';

const state = vi.hoisted(() => ({
  differences: { data: undefined as unknown, isPending: false, isError: false, refetch: () => {} },
  mutate: vi.fn(),
}));

vi.mock('@/hooks/usePatterns', () => ({
  useDifferences: () => state.differences,
  useDifferenceVerdict: () => ({ mutate: state.mutate, isPending: false }),
}));

import { InsightsScreen, sentence } from './InsightsScreen';

function diff(patternId: string, otherId: string, verdict: Difference['verdict'] = null): Difference {
  return { patternId, patternName: `Pattern ${patternId}`, otherId, otherName: `Pattern ${otherId}`,
           worse: 5, worseTotal: 6, better: 1, betterTotal: 7, verdict, patternVerdict: null };
}

function show(differences: Difference[]) {
  state.differences = { ...state.differences, data: { differences } };
  render(<MemoryRouter><InsightsScreen /></MemoryRouter>);
}

describe('Insights', () => {
  it('reads a difference as a sentence with both sides counted', () => {
    const s = sentence(diff('a', 'b'));
    expect(`${s.lead} ${s.worse}, ${s.better}`).toBe(
      'When pattern a came up, pattern b was there 5 of 6 times it went worse, and 1 of 7 times it went better.');
  });

  it('puts the ones waiting for a verdict first', () => {
    show([diff('a', 'b', { verdict: 'rings_true', note: null }), diff('c', 'd')]);
    const cards = screen.getAllByRole('article');
    expect(cards[0]).toHaveAccessibleName('Pattern c and Pattern d');
    expect(screen.getByText('judged · 1')).toBeInTheDocument();
  });

  it('sends the verdict for that pair', () => {
    show([diff('c', 'd')]);
    fireEvent.click(within(screen.getByRole('article')).getByText('rings true'));
    expect(state.mutate).toHaveBeenCalledWith({ patternId: 'c', otherId: 'd', verdict: 'rings_true' });
  });

  it('says what an insight needs when there are none', () => {
    show([]);
    expect(screen.getByText('No differences yet.')).toBeInTheDocument();
  });
});

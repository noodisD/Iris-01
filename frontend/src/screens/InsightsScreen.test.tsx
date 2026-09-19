/**
 * An empty Insights screen has six meanings, and the owner is told which.
 *
 * It used to give one answer to all of them. "No patterns yet" when the owner
 * had simply not written lately, or when their own filter hid what IRIS found,
 * is a false statement about their life. These pin the sentence for each case.
 */
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { InsightCoverage } from '@/types/api';

const state = vi.hoisted(() => ({ coverage: undefined as unknown }));

vi.mock('@/hooks/useInsights', () => ({
  useInsights: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
  useInsight: () => ({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() }),
  useInsightsCoverage: () => ({ data: state.coverage }),
}));

import { InsightsScreen } from './InsightsScreen';

const base: InsightCoverage = {
  available: true, windowDays: 21, observedDaysInWindow: 5, observedDaysRequired: 3,
  lastEntryOn: '2026-09-15', daysSinceLastEntry: 4, supportsCurrentState: true,
  entries: 182, themes: 20, entriesInThemes: 110,
  suppressedByFilter: 0, hiddenByStatus: 0, admitted: 0,
};

function showWith(overrides: Partial<InsightCoverage>) {
  state.coverage = { ...base, ...overrides };
  render(<MemoryRouter><InsightsScreen /></MemoryRouter>);
}

describe('an empty Insights screen says which kind of empty it is', () => {
  it('nothing written yet', () => {
    showWith({ entries: 0 });
    expect(screen.getByText('No patterns yet.')).toBeInTheDocument();
  });

  it('the check failed — not a measured absence', () => {
    showWith({ available: false });
    expect(screen.getByText("Iris can't tell right now.")).toBeInTheDocument();
    expect(screen.queryByText('No patterns yet.')).toBeNull();
  });

  it('nothing written lately — the entries are still there', () => {
    showWith({ observedDaysInWindow: 0 });
    expect(screen.getByText(/^Nothing written since/)).toBeInTheDocument();
    expect(screen.getByText(/Your 182 entries are still here/)).toBeInTheDocument();
  });

  it('not enough written lately to describe now', () => {
    showWith({ observedDaysInWindow: 1, supportsCurrentState: false });
    expect(screen.getByText('Not enough written lately.')).toBeInTheDocument();
  });

  it("the owner's own filter hid what was found", () => {
    showWith({ suppressedByFilter: 3 });
    expect(screen.getByText('Hidden by your settings.')).toBeInTheDocument();
    expect(screen.getByText(/That is your filter working, not an absence/)).toBeInTheDocument();
  });

  it('everything found has been dealt with', () => {
    showWith({ admitted: 4, hiddenByStatus: 4 });
    expect(screen.getByText('All caught up.')).toBeInTheDocument();
  });

  it('plenty written, nothing recurring', () => {
    showWith({});
    expect(screen.getByText('Nothing measurable about now.')).toBeInTheDocument();
  });
});

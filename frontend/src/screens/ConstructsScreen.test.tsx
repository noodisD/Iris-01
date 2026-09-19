/**
 * Confirming a pattern counts what was written, never what was done.
 *
 * A verified quote proves a subject appears in the writing; it does not prove
 * the thing happened. The confirm button, and the line under it, are the owner's
 * only statement of what they are agreeing to (ADR-0016).
 */
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { ConstructCandidate } from '@/types/api';

// Hoisted with vi.mock, which runs before this file's other top-level code.
const { mutation, candidate } = vi.hoisted(() => {
  const candidate: ConstructCandidate = {
    id: '35', claim: 'Chess openings come up again and again', summary: 'chess openings',
    origin: 'observed', claimKind: 'mention', spanStart: '2025-01-05', spanEnd: '2025-06-01',
    quotes: [
      { text: 'went all in on the opening I was most certain about', entryId: '12',
        sourceType: 'reflection', citable: true },
      { text: 'the same opening again tonight', entryId: null,
        sourceType: 'import_item', citable: false },
    ],
  };
  return { mutation: () => ({ mutate: () => {}, isPending: false }), candidate };
});

vi.mock('@/hooks/useConstructs', () => ({
  useConstructCandidates: () => ({ data: [candidate], isLoading: false, isError: false, refetch: vi.fn() }),
  useConfirmConstruct: mutation,
  useRejectConstruct: mutation,
  useDiscoverConstructs: mutation,
  useLastRun: () => ({ data: null }),
}));

import { ConstructsScreen, RunSummary } from './ConstructsScreen';
import type { DiscoveryRun } from '@/types/api';

describe('confirming a construct', () => {
  it('counts writing, and says it does not count actions', () => {
    render(<MemoryRouter><ConstructsScreen /></MemoryRouter>);
    expect(screen.getByRole('button', { name: 'Yes — count this in my writing' })).toBeInTheDocument();
    expect(screen.getByText(/Not how often you did it\./)).toBeInTheDocument();
    expect(screen.getByText('iris noticed · counts what you wrote about')).toBeInTheDocument();
  });

  it('says an undated recording is never counted', () => {
    render(<MemoryRouter><ConstructsScreen /></MemoryRouter>);
    expect(screen.getByText(/undated, so it is never counted/)).toBeInTheDocument();
  });
});

describe('the last read', () => {
  const run = (over: Partial<DiscoveryRun> = {}, dropped: Partial<DiscoveryRun['dropped']> = {}): DiscoveryRun => ({
    status: 'complete', startedAt: '2026-09-19T20:00:00Z', finishedAt: '2026-09-19T20:05:00Z',
    entriesRead: 180, passesPlanned: 6, passesCompleted: 6, rawFindings: 12, staged: 4,
    dropped: { mergedAway: 3, unchecked: 1, incomplete: 3, denied: 1, tooFewSupporting: 0,
               alreadyDecided: 0, notEmbedded: 0, ...dropped },
    dropsRecorded: true, ...over,
  });

  it('says how many findings support could not be checked for', () => {
    render(<RunSummary run={run()} />);
    const line = screen.getByRole('status');
    expect(line).toHaveTextContent('12 findings, 4 proposals.');
    expect(line).toHaveTextContent('4 because support could not be checked');
    expect(line).toHaveTextContent('1 because a quote denied the claim');
    expect(line).not.toHaveTextContent('too few');
  });

  it('says when a read did not finish', () => {
    render(<RunSummary run={run({ status: 'partial', passesCompleted: 4 })} />);
    expect(screen.getByRole('status')).toHaveTextContent('4 of 6 passes finished.');
  });

  it('does not invent reasons for a read made before they were counted', () => {
    render(<RunSummary run={run({ dropsRecorded: false }, { mergedAway: 0, unchecked: 0, incomplete: 0, denied: 0 })} />);
    expect(screen.getByRole('status')).toHaveTextContent('before IRIS counted what it let go');
  });
});

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
}));

import { ConstructsScreen } from './ConstructsScreen';

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

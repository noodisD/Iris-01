/**
 * An import cannot land while an entry's date is an open question.
 *
 * A reflection's date becomes the time every engine measures it against, so a
 * guessed date is not a small inaccuracy (ADR-0013). The server refuses such a
 * commit; the screen must not offer it, and must say what to do.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ImportBatch, ImportEntry } from '@/types/api';

const state = vi.hoisted(() => ({ entries: [] as ImportEntry[], bulk: [] as unknown[] }));

vi.mock('@/hooks/useImport', () => ({
  useImportEntries: () => ({ data: state.entries, isLoading: false }),
  useImportAdapters: () => ({ data: [] }),
  useImportActions: () => new Proxy({}, {
    get: (_t, op) => op === 'bulk'
      ? { mutate: (v: unknown) => state.bulk.push(v), isPending: false }
      : { mutate: vi.fn(), isPending: false },
  }),
}));

import { Review } from './ImportScreen';

function batch(needsDate: number, over: Partial<ImportBatch> = {},
               counts: Partial<ImportBatch['counts']> = {}): ImportBatch {
  return {
    id: '9', kind: 'text', adapter: 'markdown', detected: [], originalFilename: 'notes.md',
    status: 'needs_review', error: null, entryCount: 5, committedCount: 0,
    createdAt: '2026-09-19T08:00:00Z',
    counts: { total: 5, staged: 5, excluded: 0, duplicate: 0, imported: 0, failed: 0,
              needsDate, awaitingTranscript: 0, earliest: null, latest: null, ...counts },
    ...over,
  };
}

beforeEach(() => { state.entries = []; state.bulk = []; });

describe('the import commit', () => {
  it('is refused while an entry has no date, and says what to do', () => {
    render(<Review batch={batch(2)} onDone={() => {}} />);
    expect(screen.getByRole('button', { name: 'Import 5 entries' })).toBeDisabled();
    expect(screen.getByText('Set or exclude the undated entries first.')).toBeInTheDocument();
  });

  it('is offered once every date is resolved', () => {
    render(<Review batch={batch(0)} onDone={() => {}} />);
    expect(screen.getByRole('button', { name: 'Import 5 entries' })).toBeEnabled();
    expect(screen.queryByText('Set or exclude the undated entries first.')).toBeNull();
  });
});


function undatedEntry(over: Partial<ImportEntry> = {}): ImportEntry {
  return {
    id: '31', sourceName: 'recording.m4a', title: null, excerpt: 'a transcript',
    occurredOn: null, dateSource: null, dateConfidence: 'unknown',
    dateUnknownAccepted: false, fileModifiedOn: null, status: 'staged',
    warnings: [], hasAudio: true, error: null, ...over,
  } as ImportEntry;
}

describe('an entry whose day cannot be recovered', () => {
  it('can be accepted as undated, which is not the same as guessing', () => {
    state.entries = [undatedEntry()];
    render(<Review batch={batch(1)} onDone={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: 'accept as undated' }));

    expect(state.bulk).toEqual([{ ids: ['31'], op: 'accept_unknown_date' }]);
  });

  it('is no longer listed as a blocker once the owner has accepted it', () => {
    state.entries = [undatedEntry({ dateUnknownAccepted: true })];
    render(<Review batch={batch(0)} onDone={() => {}} />);

    expect(screen.queryByRole('button', { name: 'accept as undated' })).toBeNull();
  });
});


describe('a batch where some entries failed', () => {
  it('says what landed and keeps the review open', () => {
    state.entries = [undatedEntry({ status: 'failed', error: 'the embedder went away',
                                    occurredOn: '2024-04-01' })];
    render(<Review batch={batch(0, { status: 'failed', error: 'the embedder went away' },
                                { imported: 4, failed: 1 })} onDone={() => {}} />);

    expect(screen.getByRole('alert')).toHaveTextContent('4 of 5 entries were imported; 1 failed.');
    expect(screen.getByRole('button', { name: 'Import 5 entries' })).toBeInTheDocument();
  });

  it('offers a failed entry another try, not exclusion', () => {
    state.entries = [undatedEntry({ status: 'failed', occurredOn: '2024-04-01' })];
    render(<Review batch={batch(0, { status: 'failed' }, { imported: 0, failed: 1 })}
                   onDone={() => {}} />);

    expect(screen.getByRole('button', { name: 'try this entry again' })).toBeInTheDocument();
  });
});

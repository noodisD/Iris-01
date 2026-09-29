/** Source-first Patterns interactions with invented accounts. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Occasion, PatternDetail, PatternSummary } from '@/types/api';

const base = { holdsWhen: [], notWhen: [], question: '', basis: null, source: null };
const coverage = {
  range: 'all' as const, asOf: '2026-09-29', recordedFrom: '2024-05-03', recordedTo: '2024-05-03',
  entryCount: 3, accountCount: 3, undatedAccountCount: 0,
};

function occasion(id: string, situation: string, tone: Occasion['tone'], entryId: string): Occasion {
  return { id, recordedOn: '2024-05-03', domain: 'garden', situation, response: 'did something',
           outcome: 'and then', explanation: null, tone, suggestedTone: tone, ownerTone: null,
           size: 'large', labelledBy: 'strong-model', ownerVerdict: null, verdictNote: null,
           citations: [{ entryId, sourceType: 'reflection', entryDate: '2024-05-03', text: situation }] };
}

const bigAccounts = [
  occasion('1', 'The seedlings died again', 'worse', '31'),
  occasion('2', 'The tomatoes failed', 'worse', '32'),
  occasion('3', 'Planned the beds in winter', 'better', '33'),
];
function summary(id: string, name: string, accounts: Occasion[], extra: Partial<PatternSummary> = {}): PatternSummary {
  const tones = { better: accounts.filter(a => a.tone === 'better').length,
    worse: accounts.filter(a => a.tone === 'worse').length,
    mixed: accounts.filter(a => a.tone === 'mixed').length };
  return { ...base, id, name, statement: `${name}.`, evidence: null, occasions: accounts.length, tones,
    entryCount: accounts.length, recordedFrom: accounts.length ? '2024-05-03' : null,
    recordedTo: accounts.length ? '2024-05-03' : null, undatedAccountCount: 0,
    examples: accounts.slice(0, 2), snapshot: 'a'.repeat(64),
    coverage: { ...coverage, entryCount: accounts.length, accountCount: accounts.length,
      recordedFrom: accounts.length ? '2024-05-03' : null, recordedTo: accounts.length ? '2024-05-03' : null },
    reviewed: 0, rejected: 0, labelledBy: [], verdict: null, ...extra };
}

const server = vi.hoisted(() => ({
  occasionVerdicts: [] as unknown[],
  patternVerdicts: [] as unknown[],
}));

vi.mock('@/api/patterns', () => ({
  getPatterns: async () => ({ patterns: [
    summary('empty-one', 'A quiet pattern', []),
    summary('big-one', 'Committed more than could be taken back', bigAccounts,
            { verdict: { verdict: 'rings_true', note: 'An existing thought' } }),
  ], coverage }),
  getPattern: async (id: string): Promise<PatternDetail> => id === 'empty-one'
    ? { pattern: { ...base, id, name: 'A quiet pattern', statement: 'Rare.', evidence: null },
        occasions: [], distinctive: [],
        coverage: { ...coverage, entryCount: 0, accountCount: 0, recordedFrom: null, recordedTo: null },
        snapshot: 'a'.repeat(64), verdict: null }
    : { pattern: { ...base, id, name: 'Committed more than could be taken back', statement: 'More was committed.',
                   evidence: 'mixed' },
        occasions: bigAccounts,
        distinctive: [],
        coverage, snapshot: 'a'.repeat(64), verdict: { verdict: 'rings_true', note: 'An existing thought' } },
  setOccasionVerdict: async (patternId: string, occasionId: string, feedback: unknown) => {
    server.occasionVerdicts.push({ patternId, occasionId, feedback });
    return { ok: true };
  },
  setPatternVerdict: async (patternId: string, feedback: unknown) => {
    server.patternVerdicts.push({ patternId, feedback });
    return { ok: true };
  },
  getDiscoveryStatus: async () => ({
    eligibleEntries: 3, currentEntries: 3, unreadEntries: 0, pendingEntries: 0,
    failedEntries: 0, excludedEntries: 0, omittedAccounts: 0, lastCompletedAt: null,
    model: 'test-model', estimatedRequests: 0, estimate: 'Approximate: no unread entries',
  }),
  refreshDiscovery: async () => ({ queuedEntries: 0 }),

}));
import { PatternsScreen } from './PatternsScreen';

function show(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/patterns" element={<PatternsScreen />} />
          <Route path="/patterns/:id" element={<PatternsScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('the library', () => {
  beforeEach(() => { server.occasionVerdicts = []; server.patternVerdicts = []; });

  it('shows personal passages before the library lens and retains the period in evidence links', async () => {
    show('/patterns?range=90d');
    const card = await screen.findByRole('article');
    expect(within(card).getAllByText('did something')).toHaveLength(2);
    expect(within(card).getByRole('link', { name: 'See examples' }))
      .toHaveAttribute('href', '/patterns/big-one?range=90d');
    const discussion = within(card).getByRole('link', { name: 'Explore with Iris' });
    const reference = JSON.parse(new URL(discussion.getAttribute('href')!, 'http://localhost').searchParams.get('evidence')!);
    expect(reference).toEqual({ kind: 'pattern', patternId: 'big-one', range: '90d', snapshot: 'a'.repeat(64) });
    expect(screen.queryByText('A quiet pattern')).toBeNull();
  });
});

describe('a pattern', () => {
  beforeEach(() => { server.occasionVerdicts = []; server.patternVerdicts = []; });

  it('groups provisional accounts and links each source citation', async () => {
    show('/patterns/big-one');
    const worse = await screen.findByRole('region', { name: 'read as worse' });
    expect(within(worse).getAllByRole('article')).toHaveLength(2);
    expect(within(screen.getByRole('region', { name: 'read as better' })).getAllByRole('article')).toHaveLength(1);
    const card = screen.getByRole('article', { name: 'occasion: The seedlings died again' });
    expect(within(card).getByRole('link', { name: 'open entry' })).toHaveAttribute('href', '/journal?entry=31');
  });

  it('preserves existing notes in judgment updates and supports note-only feedback', async () => {
    show('/patterns/big-one');
    const card = await screen.findByRole('article', { name: 'occasion: The tomatoes failed' });
    fireEvent.change(within(card).getByRole('textbox', { name: 'Note about this account' }),
      { target: { value: 'Needs another look' } });
    fireEvent.click(within(card).getByRole('button', { name: 'Save note' }));
    await waitFor(() => expect(server.occasionVerdicts).toContainEqual({
      patternId: 'big-one', occasionId: '2',
      feedback: { verdict: null, note: 'Needs another look', ownerTone: null },
    }));
    fireEvent.click(within(card).getByRole('radio', { name: 'Not this' }));
    fireEvent.click(screen.getByRole('radio', { name: "Doesn't ring true" }));
    await waitFor(() => expect(server.occasionVerdicts).toContainEqual({
      patternId: 'big-one', occasionId: '2',
      feedback: { verdict: 'no', note: 'Needs another look', ownerTone: null },
    }));
    expect(server.patternVerdicts).toContainEqual({
      patternId: 'big-one', feedback: { verdict: 'does_not', note: 'An existing thought' },
    });
  });

  it('does not present a library-only lens as a personal finding', async () => {
    show('/patterns/empty-one');
    expect(await screen.findByText(/No source-backed example in this reading/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'open entry' })).toBeNull();
  });
});

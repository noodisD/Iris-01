/**
 * The Patterns screen: the library, a pattern's occasions on both sides, what
 * else differed, and the owner's two verdicts.
 *
 * Every occasion is invented.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Occasion, PatternDetail, PatternSummary } from '@/types/api';

const base = { holdsWhen: [], notWhen: [], question: '', basis: null, source: null };

function summary(id: string, name: string, tones: PatternSummary['tones'], extra: Partial<PatternSummary> = {}): PatternSummary {
  const occasions = tones.better + tones.worse + tones.mixed;
  return { ...base, id, name, statement: `${name}.`, evidence: null, occasions, tones,
           reviewed: 0, rejected: 0, labelledBy: [], verdict: null, ...extra };
}

function occasion(id: string, situation: string, tone: Occasion['tone'], entryId: string): Occasion {
  return { id, occurredOn: '2024-05-03', domain: 'garden', situation, response: 'did something',
           outcome: 'and then', explanation: null, tone, size: 'large', labelledBy: 'strong-model',
           ownerVerdict: null, verdictNote: null,
           citations: [{ entryId, sourceType: 'reflection', entryDate: '2024-05-03', text: situation }] };
}

const server = vi.hoisted(() => ({
  occasionVerdicts: [] as unknown[],
  patternVerdicts: [] as unknown[],
}));

vi.mock('@/api/patterns', () => ({
  getPatterns: async () => ({ patterns: [
    summary('empty-one', 'A quiet pattern', { better: 0, worse: 0, mixed: 0 }),
    summary('big-one', 'Committed more than could be taken back', { better: 1, worse: 2, mixed: 0 },
            { verdict: { verdict: 'rings_true', note: null } }),
  ] }),
  getPattern: async (id: string): Promise<PatternDetail> => id === 'empty-one'
    ? { pattern: { ...base, id, name: 'A quiet pattern', statement: 'Rare.', evidence: null },
        occasions: [], alsoTrue: { better: {}, worse: {} }, distinctive: [], verdict: null }
    : { pattern: { ...base, id, name: 'Committed more than could be taken back', statement: 'More was committed.',
                   evidence: 'mixed' },
        occasions: [occasion('1', 'The seedlings died again', 'worse', '31'),
                    occasion('2', 'The tomatoes failed', 'worse', '32'),
                    occasion('3', 'Planned the beds in winter', 'better', '33')],
        alsoTrue: { better: {}, worse: { 'continuing-after-a-setback': 2 } },
        distinctive: [{ patternId: 'continuing-after-a-setback', name: 'Carried on after a setback', better: 0, worse: 2 }],
        verdict: { verdict: 'rings_true', note: null } },
  setOccasionVerdict: async (patternId: string, occasionId: string, verdict: string | null) => {
    server.occasionVerdicts.push({ patternId, occasionId, verdict });
    return { ok: true };
  },
  setPatternVerdict: async (patternId: string, verdict: string) => {
    server.patternVerdicts.push({ patternId, verdict });
    return { ok: true };
  },
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

  it('lists patterns with the most occasions first, and says when none were found', async () => {
    show('/patterns');
    const nav = await screen.findByRole('navigation', { name: 'Patterns' });
    const links = within(nav).getAllByRole('link');
    expect(links[0]).toHaveTextContent('Committed more than could be taken back');
    expect(links[0]).toHaveTextContent('2 worse · 1 better · rings true');
    expect(links[1]).toHaveTextContent('none found');
    expect(screen.getByText('Pick a pattern.')).toBeInTheDocument();
  });
});

describe('a pattern', () => {
  beforeEach(() => { server.occasionVerdicts = []; server.patternVerdicts = []; });

  it('shows both sides, what else differed, and links each quote to its entry', async () => {
    show('/patterns/big-one');
    const worse = await screen.findByRole('region', { name: 'went worse' });
    expect(within(worse).getByText('went worse · 2')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'went better' })).getByText('went better · 1')).toBeInTheDocument();
    const differed = screen.getByRole('region', { name: 'what else differed' });
    expect(within(differed).getByText('Carried on after a setback')).toBeInTheDocument();
    expect(within(differed).getByText('2 worse · 0 better')).toBeInTheDocument();
    const card = screen.getByRole('article', { name: 'occasion: The seedlings died again' });
    expect(within(card).getByRole('link', { name: 'open entry' })).toHaveAttribute('href', '/journal?entry=31');
  });

  it('records whether an occasion belongs, and whether the pattern rings true', async () => {
    show('/patterns/big-one');
    const card = await screen.findByRole('article', { name: 'occasion: The tomatoes failed' });
    fireEvent.click(within(card).getByRole('button', { name: 'not this' }));
    fireEvent.click(screen.getByRole('button', { name: "doesn't ring true" }));
    await waitFor(() => expect(server.occasionVerdicts).toEqual([{ patternId: 'big-one', occasionId: '2', verdict: 'no' }]));
    expect(server.patternVerdicts).toEqual([{ patternId: 'big-one', verdict: 'does_not' }]);
  });

  it('says a pattern with no occasions may be sparsely labelled rather than rare', async () => {
    show('/patterns/empty-one');
    expect(await screen.findByText(/labelled\s+sparsely/)).toBeInTheDocument();
  });
});

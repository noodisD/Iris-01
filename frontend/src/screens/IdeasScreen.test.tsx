import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

const { reject, confirmIdea, rejectLink, confirmLink, updateIdea, foldIdea, fixtures } = vi.hoisted(() => {
  const review = {
    ideas: [{
      idea: {
        id: '7', statement: 'Price controls destroy the information prices carry about scarcity.',
        domain: 'economics', status: 'candidate', position: 'exploring',
        citationCount: 1, pendingCitationCount: 1, firstWrittenOn: '2024-01-01',
        lastWrittenOn: '2024-01-01', undatedCount: 0, needsEvidence: false,
      },
      citations: [{
        id: '3', entryId: '12', entryDate: '2024-01-01',
        text: 'When a government fixes prices, it destroys the signal that tells people what is scarce.',
        stance: 'endorsed', status: 'candidate',
      }],
      onRecord: [],
    }, {
      idea: {
        id: '10', statement: 'Rules should bind the people who write them.',
        domain: 'ethics', status: 'active', position: 'endorsed',
        citationCount: 1, pendingCitationCount: 1, firstWrittenOn: '2025-03-01',
        lastWrittenOn: '2025-03-01', undatedCount: 0, needsEvidence: false,
      },
      citations: [{
        id: '11', entryId: '13', entryDate: '2025-03-01',
        text: 'A rule that exempts its authors is not a rule at all.',
        stance: 'endorsed', status: 'candidate',
      }],
      onRecord: [{
        id: '14', entryId: '15', entryDate: '2024-02-01',
        text: 'Whoever writes the rule should live under it.',
        stance: 'endorsed', status: 'accepted',
      }, {
        id: '16', entryId: '17', entryDate: '2024-11-01',
        text: 'A lawmaker exempt from the law is a ruler.',
        stance: 'questioned', status: 'accepted',
      }],
    }],
    links: [],
    lastRun: null,
  };
  const framework = {
    ideas: [
      {
        id: '7', statement: 'Price controls destroy the information prices carry about scarcity.',
        domain: 'economics', status: 'active', position: 'endorsed',
        citationCount: 1, pendingCitationCount: 0, firstWrittenOn: '2024-01-01',
        lastWrittenOn: '2024-01-01', undatedCount: 0, needsEvidence: false,
      },
      {
        id: '8', statement: 'A central planner can know enough to set better prices than a market.',
        domain: 'economics', status: 'active', position: 'endorsed',
        citationCount: 1, pendingCitationCount: 0, firstWrittenOn: '2025-02-01',
        lastWrittenOn: '2025-02-01', undatedCount: 0, needsEvidence: false,
      },
    ],
    links: [{
      id: '4', fromIdeaId: '7', toIdeaId: '8', kind: 'contradicts', status: 'accepted',
      rationale: 'These cannot both be accepted about the same prices.',
      fromStatement: 'Price controls destroy the information prices carry about scarcity.',
      toStatement: 'A central planner can know enough to set better prices than a market.',
    }],
    tensionIds: ['4'],
    foundationIds: [],
    unconnectedIds: [],
    lastRun: null,
  };
  const detail = {
    idea: framework.ideas[0],
    citations: [],
    links: [],
    critiques: [{
      id: '9', origin: 'iris', createdAt: '2026-09-24T12:00:00Z', model: 'scripted',
      promptVersion: 'abc', basis: {}, isCurrent: true,
      content: {
        objections: [{ argument: 'A signal can be noisy.', question: 'What would count?' }],
        possiblePremises: [],
        relatedThought: [],
      },
    }],
    page: {
      notes: 'It follows from [[A central planner can know enough to set better prices than a market.|the planner claim]], not [[Some idea never written]].',
      notesUpdatedAt: '2026-09-27T10:00:00Z',
      links: { 'A central planner can know enough to set better prices than a market.': '8' },
      backlinks: [{ id: '8', statement: 'A central planner can know enough to set better prices than a market.', status: 'active' }],
    },
  };
  const linkedDetail = {
    idea: framework.ideas[1],
    citations: [],
    links: [{
      id: '5', fromIdeaId: '7', toIdeaId: '8', kind: 'depends_on', status: 'accepted',
      rationale: 'The planner claim relies on the price claim.',
      fromStatement: framework.ideas[0].statement,
      toStatement: framework.ideas[1].statement,
    }],
    critiques: [],
    page: { notes: '', notesUpdatedAt: null, links: {}, backlinks: [] },
  };
  return {
    reject: vi.fn(),
    confirmIdea: vi.fn(),
    rejectLink: vi.fn(),
    confirmLink: vi.fn(),
    updateIdea: vi.fn(),
    foldIdea: vi.fn(),
    fixtures: { review, framework, detail, linkedDetail },
  };
});

// The 3D graph needs WebGL; its own tests cover it.
vi.mock('@/components/IdeaGraph', () => ({ IdeaGraph: () => <div role="img" aria-label="Ideas graph" /> }));

vi.mock('@/hooks/useIdeas', () => ({
  useIdeasFramework: () => ({ data: fixtures.framework, isLoading: false, isError: false, refetch: vi.fn() }),
  useIdeaReview: () => ({ data: fixtures.review, isLoading: false, isError: false, refetch: vi.fn() }),
  useIdea: (id?: string) => ({ data: id === '8' ? fixtures.linkedDetail : fixtures.detail, isLoading: false, isError: false, refetch: vi.fn() }),
  useDiscoverIdeas: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useDiscoverMeanings: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useMeaningEstimate: () => ({ data: { ideas: 3, calls: 1, tokensIn: 900, estimate: '0k tokens in on m, about $0.01' }, isPending: false, isError: false }),
  useConfirmIdea: () => ({ mutate: confirmIdea, isPending: false, error: null }),
  useRejectIdea: () => ({ mutate: reject, isPending: false, error: null }),
  useRejectIdeaCitations: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useFoldIdea: () => ({ mutate: foldIdea, isPending: false, error: null }),
  useUpdateIdea: () => ({ mutate: updateIdea, isPending: false, error: null, reset: vi.fn() }),
  useSaveIdeaNotes: () => ({ mutate: vi.fn(), isPending: false, error: null, refresh: vi.fn() }),
  useDiscoverIdeaLinks: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useConfirmIdeaLink: () => ({ mutate: confirmLink, isPending: false, error: null }),
  useRejectIdeaLink: () => ({ mutate: rejectLink, isPending: false, error: null }),
  useCritiqueIdea: () => ({ mutate: vi.fn(), isPending: false, error: null }),
}));

import { IdeasScreen } from './IdeasScreen';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/ideas" element={<IdeasScreen />} />
        <Route path="/ideas/:id" element={<IdeasScreen />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('Ideas screen', () => {
  it('shows a proposal with its historical stance', () => {
    renderAt('/ideas?view=review');
    const card = screen.getByText('Price controls destroy the information prices carry about scarcity.').closest('article')!;
    const view = within(card);
    expect(view.getByText('Price controls destroy the information prices carry about scarcity.')).toBeInTheDocument();
    expect(view.getByText(/When a government fixes prices/)).toBeInTheDocument();
    expect(view.getByText('You endorsed this then')).toBeInTheDocument();
    expect(view.getByRole('button', { name: 'Add to framework' })).toBeInTheDocument();
  });

  it('shows what finding related ideas would send and cost before anything is sent', () => {
    renderAt('/ideas?view=review');
    fireEvent.click(screen.getByRole('button', { name: 'Find related ideas' }));
    const dialog = screen.getByRole('dialog', { name: 'Find related ideas' });
    expect(dialog).toHaveTextContent('Sends your 3 accepted idea statements, and no journal text');
    expect(dialog).toHaveTextContent('about $0.01');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('opens on the map, and lists on request', async () => {
    renderAt('/ideas');
    expect(await screen.findByRole('img', { name: 'Ideas graph' })).toBeInTheDocument();
    // The index beside the map names each idea, grouped by area.
    const index = screen.getByRole('navigation', { name: 'Ideas on the map' });
    expect(within(index).getByRole('heading', { name: 'Economics' })).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'List' }));
    expect(screen.queryByRole('img', { name: 'Ideas graph' })).toBeNull();
    expect(screen.getByRole('heading', { name: /Economics/ })).toBeInTheDocument();
  });

  it('filters by area from the chips', () => {
    renderAt('/ideas?view=list');
    fireEvent.click(screen.getByRole('button', { name: /Economics/ }));
    expect(screen.getByRole('button', { name: /Economics/ })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.change(screen.getByLabelText('Search your ideas'), { target: { value: 'planner' } });
    const rows = screen.getAllByRole('listitem').map(item => item.textContent);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatch(/central planner/);
  });

  it('shows an endorsed pair as an open tension', () => {
    renderAt('/ideas?view=list');
    const section = screen.getByRole('heading', { name: 'Open tensions' }).closest('section')!;
    const view = within(section);
    expect(view.getByText('Price controls destroy the information prices carry about scarcity.')).toBeInTheDocument();
    expect(view.getByText('A central planner can know enough to set better prices than a market.')).toBeInTheDocument();
    expect(view.getByText('contradicts')).toBeInTheDocument();
  });

  it('labels a critique as Iris and does not save it as the owner position', () => {
    renderAt('/ideas/7');
    expect(screen.getByText('Generated by Iris — not your recorded position')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /as my (belief|position)|save critique|add critique/i })).not.toBeInTheDocument();
  });

  it('does not reject when removal is cancelled', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    reject.mockClear();
    renderAt('/ideas/7');
    fireEvent.click(screen.getByRole('button', { name: 'Remove from framework' }));
    expect(reject).not.toHaveBeenCalled();
  });

  it('keeps an active idea\'s saved position and domain when accepting new quotes', () => {
    renderAt('/ideas?view=review');
    const card = screen.getByText('Rules should bind the people who write them.').closest('article')!;
    const view = within(card);
    expect(view.getByLabelText(/^Position/)).toHaveValue('endorsed');
    expect(view.getByLabelText(/^Domain/)).toHaveValue('ethics');
    fireEvent.click(view.getByRole('button', { name: 'Accept new quotes' }));
    expect(confirmIdea).toHaveBeenCalledWith({
      id: '10',
      body: { citationIds: ['11'], position: 'endorsed', domain: 'ethics' },
    });
  });

  it('offers and guards removal of an accepted connection', () => {
    renderAt('/ideas/8');
    const buttons = screen.getAllByRole('button', { name: 'Remove from framework' });
    expect(buttons).toHaveLength(2);
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    rejectLink.mockClear();
    fireEvent.click(buttons[0]);
    expect(rejectLink).not.toHaveBeenCalled();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    fireEvent.click(buttons[0]);
    expect(rejectLink).toHaveBeenCalledWith('5');
  });
});

describe('a proposed link between two ideas', () => {
  const proposal = {
    id: '21', fromIdeaId: '7', toIdeaId: '10', kind: 'same_meaning', status: 'candidate',
    rationale: 'Both rest on one principle.',
    fromStatement: 'Price controls destroy the information prices carry about scarcity.',
    toStatement: 'Rules should bind the people who write them.',
  };

  it('is accepted as proposed, or as the relation the owner names', () => {
    fixtures.review.links = [proposal] as never;
    try {
      renderAt('/ideas?view=review');
      const card = screen.getByRole('article', { name: /means the same as/ });
      expect(within(card).queryByRole('button', { name: 'Swap the two ideas' })).toBeNull();

      fireEvent.change(within(card).getByLabelText('Relation'), { target: { value: 'applies' } });
      fireEvent.click(within(card).getByRole('button', { name: 'Swap the two ideas' }));
      const ends = within(card).getAllByRole('link').map(a => a.textContent);
      expect(ends).toEqual([proposal.toStatement, proposal.fromStatement]);

      fireEvent.click(within(card).getByRole('button', { name: 'Accept with this relation' }));
      expect(confirmLink).toHaveBeenCalledWith({ id: '21', as: { kind: 'applies', reverse: true } });
    } finally {
      fixtures.review.links = [];
    }
  });

  it('renames an idea on its own page', () => {
    renderAt('/ideas/7');
    fireEvent.click(screen.getByRole('button', { name: 'Rename this idea' }));
    const field = screen.getByRole('textbox', { name: 'Wording of this idea' });
    fireEvent.change(field, { target: { value: '  Fixed prices hide   scarcity. ' } });
    fireEvent.keyDown(field, { key: 'Enter' });
    expect(updateIdea).toHaveBeenCalledWith(
      { id: '7', body: { statement: 'Fixed prices hide scarcity.' } }, expect.anything(),
    );
  });

  it('keeps the old wording when renaming is cancelled', () => {
    updateIdea.mockClear();
    renderAt('/ideas/7');
    fireEvent.click(screen.getByRole('button', { name: 'Rename this idea' }));
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Wording of this idea' }), { key: 'Escape' });
    expect(updateIdea).not.toHaveBeenCalled();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Price controls destroy');
  });

  it('shows notes with links to other ideas, and the ideas that link here', () => {
    renderAt('/ideas/7');
    const notes = screen.getByRole('region', { name: 'Notes' });
    expect(within(notes).getByRole('link', { name: 'the planner claim' })).toHaveAttribute('href', '/ideas/8');
    expect(within(notes).getByText('Some idea never written')).toHaveAttribute('title', 'No idea has this wording yet');
    const backlinks = screen.getByRole('region', { name: /Linked from/ });
    expect(within(backlinks).getByRole('link', { name: /A central planner/ })).toHaveAttribute('href', '/ideas/8');
  });

  it('invites notes on an idea that has none', () => {
    renderAt('/ideas/8');
    expect(screen.getByRole('button', { name: /Type \[\[ to link another idea/ })).toBeInTheDocument();
    expect(screen.getByText("No other idea's notes link here yet.")).toBeInTheDocument();
  });

  it('marks new quotes apart from the ones already on record', () => {
    renderAt('/ideas?view=review');
    const card = screen.getByText('Rules should bind the people who write them.').closest('article')!;
    const view = within(card);
    expect(view.getByText('1 new passage')).toBeInTheDocument();
    expect(view.getByText('New')).toBeInTheDocument();
    const record = view.getByText(/Already on record: 2 quotes, from February 2024 to November 2024/);
    expect(record.tagName).toBe('SUMMARY');
    expect(record.closest('details')).not.toHaveAttribute('open');
    expect(view.getByText(/Whoever writes the rule/)).toBeInTheDocument();
  });

  it('folds a proposal into an idea already held', () => {
    renderAt('/ideas?view=review');
    const card = screen.getByText('Price controls destroy the information prices carry about scarcity.').closest('article')!;
    const view = within(card);
    fireEvent.click(view.getByRole('button', { name: "It's an idea I already hold" }));
    const options = within(view.getByRole('list', { name: 'Ideas you hold' })).getAllByRole('button');
    // The proposal itself is never offered as the idea it folds into.
    expect(options.map(option => option.textContent)).toEqual([
      'A central planner can know enough to set better prices than a market.',
    ]);
    fireEvent.click(options[0]);
    fireEvent.click(view.getByRole('button', { name: 'Add its quotes to this idea' }));
    expect(foldIdea).toHaveBeenCalledWith({ id: '7', intoId: '8' }, expect.anything());
  });

  it('merges a held idea into another from its page', () => {
    foldIdea.mockClear();
    renderAt('/ideas/7');
    fireEvent.click(screen.getByRole('button', { name: 'Merge into another idea' }));
    expect(screen.getByText(/It will be kept, with everything from this one/)).toBeInTheDocument();
    const options = within(screen.getByRole('list', { name: 'Ideas you hold' })).getAllByRole('button');
    fireEvent.click(options[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Merge into this idea' }));
    expect(foldIdea).toHaveBeenCalledWith({ id: '7', intoId: '8' }, expect.anything());
  });
});

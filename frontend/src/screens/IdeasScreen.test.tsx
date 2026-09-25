import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

const { reject, confirmIdea, rejectLink, fixtures } = vi.hoisted(() => {
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
  };
  return {
    reject: vi.fn(),
    confirmIdea: vi.fn(),
    rejectLink: vi.fn(),
    fixtures: { review, framework, detail, linkedDetail },
  };
});

vi.mock('@/hooks/useIdeas', () => ({
  useIdeasFramework: () => ({ data: fixtures.framework, isLoading: false, isError: false, refetch: vi.fn() }),
  useIdeaReview: () => ({ data: fixtures.review, isLoading: false, isError: false, refetch: vi.fn() }),
  useIdea: (id?: string) => ({ data: id === '8' ? fixtures.linkedDetail : fixtures.detail, isLoading: false, isError: false, refetch: vi.fn() }),
  useDiscoverIdeas: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useConfirmIdea: () => ({ mutate: confirmIdea, isPending: false, error: null }),
  useRejectIdea: () => ({ mutate: reject, isPending: false, error: null }),
  useRejectIdeaCitations: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useUpdateIdea: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useDiscoverIdeaLinks: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useConfirmIdeaLink: () => ({ mutate: vi.fn(), isPending: false, error: null }),
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

  it('opens on the graph, and lists on request', () => {
    renderAt('/ideas');
    expect(screen.getByRole('img', { name: 'Ideas graph' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'list' }));
    expect(screen.queryByRole('img', { name: 'Ideas graph' })).toBeNull();
  });

  it('shows an endorsed pair as an open tension', () => {
    renderAt('/ideas');
    fireEvent.click(screen.getByRole('button', { name: 'list' }));
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

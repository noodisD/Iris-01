/** The ideas graph: what is drawn, what proposals look like, and where a click goes. */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { IdeaLink, IdeaSummary } from '@/types/api';
import { IdeaGraph, buildGraph } from './IdeaGraph';

function idea(id: string, domain: IdeaSummary['domain'] = 'ethics', citationCount = 1): IdeaSummary {
  return { id, statement: `Statement ${id}`, domain, status: 'active', position: 'endorsed', citationCount,
           pendingCitationCount: 0, firstWrittenOn: null, lastWrittenOn: null, undatedCount: 0, needsEvidence: false };
}
function link(id: string, from: string, to: string, kind: IdeaLink['kind'] = 'supports'): IdeaLink {
  return { id, fromIdeaId: from, toIdeaId: to, kind, rationale: '', status: 'accepted', fromStatement: '', toStatement: '' };
}
const label = (d: string) => d.toUpperCase();

describe('buildGraph', () => {
  it('draws each idea, one hub per area, and the accepted links', () => {
    const g = buildGraph({ ideas: [idea('1'), idea('2'), idea('3', 'learning')], links: [link('l', '1', '2')],
                           showAreas: true, areaLabel: label });
    expect(g.nodes.map(n => n.id).sort()).toEqual(['a:ethics', 'a:learning', 'i:1', 'i:2', 'i:3']);
    expect(g.lines.filter(l => l.target.startsWith('a:'))).toHaveLength(3);
    expect(g.lines.find(l => l.source === 'i:1' && l.target === 'i:2')?.dashed).toBe(false);
  });

  it('draws proposals hollow and dashed, and never twice', () => {
    const g = buildGraph({ ideas: [idea('1')], links: [], proposedIdeas: [idea('1'), idea('9')],
                           proposedLinks: [link('p', '1', '9', 'contradicts')], showAreas: false, areaLabel: label });
    expect(g.nodes.map(n => [n.id, n.proposed])).toEqual([['i:1', false], ['i:9', true]]);
    expect(g.lines).toEqual([expect.objectContaining({ source: 'i:1', target: 'i:9', dashed: true })]);
  });

  it('leaves out links to ideas that are not drawn', () => {
    const g = buildGraph({ ideas: [idea('1')], links: [link('l', '1', 'hidden')], showAreas: false, areaLabel: label });
    expect(g.lines).toEqual([]);
  });

  it('makes an idea written more often a bigger dot', () => {
    const g = buildGraph({ ideas: [idea('1', 'ethics', 1), idea('2', 'ethics', 9)], links: [], showAreas: false, areaLabel: label });
    expect(g.nodes[1].r).toBeGreaterThan(g.nodes[0].r);
  });
});

function Where() {
  return <div data-testid="where">{useLocation().pathname + useLocation().search}</div>;
}

describe('IdeaGraph', () => {
  it('opens an idea on click, and sends a proposal to Review', () => {
    render(
      <MemoryRouter initialEntries={['/ideas']}>
        <Routes><Route path="*" element={<>
          <IdeaGraph ideas={[idea('1')]} links={[]} proposedIdeas={[idea('9')]} showAreas areaLabel={label} />
          <Where />
        </>} /></Routes>
      </MemoryRouter>,
    );
    const accepted = screen.getByRole('button', { name: 'Idea: Statement 1' });
    act(() => { fireEvent.pointerDown(accepted); fireEvent.pointerUp(accepted); });
    expect(screen.getByTestId('where')).toHaveTextContent('/ideas/1');
    const proposed = screen.getByRole('button', { name: 'Proposed idea: Statement 9' });
    act(() => { fireEvent.pointerDown(proposed); fireEvent.pointerUp(proposed); });
    expect(screen.getByTestId('where')).toHaveTextContent('/ideas?view=review');
    expect(screen.getByRole('button', { name: 'Area: ETHICS' })).toBeInTheDocument();
  });
});

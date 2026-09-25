/** The ideas graph: what is drawn, how proposals and shared meanings look, and where a click goes. */
import { act, render } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { IdeaLink, IdeaSummary } from '@/types/api';

// WebGL does not exist here, so the 3D library is a recorder.
const lib = vi.hoisted(() => ({ instance: null as null | Record<string, unknown> & { handlers: Record<string, (...a: unknown[]) => void>; data: unknown } }));
vi.mock('3d-force-graph', () => ({
  default: class {
    constructor() {
      const state = { handlers: {} as Record<string, (...a: unknown[]) => void>, data: null as unknown };
      const proxy: unknown = new Proxy(state, {
        get: (target, prop: string) => {
          if (prop === 'handlers' || prop === 'data') return target[prop];
          if (prop === 'graphData') return (d?: unknown) => (d === undefined ? target.data ?? { links: [] } : ((target.data = d), proxy));
          if (prop === 'd3Force') return () => ({ distance: () => undefined });
          if (prop.startsWith('on')) return (fn: (...a: unknown[]) => void) => { target.handlers[prop] = fn; return proxy; };
          return () => proxy;
        },
      });
      lib.instance = proxy as never;
      return proxy as never;
    }
  },
}));

import { IdeaGraph, buildGraph, neighbourhood } from './IdeaGraph';

function idea(id: string, domain: IdeaSummary['domain'] = 'ethics', citationCount = 1): IdeaSummary {
  return { id, statement: `Statement ${id}`, domain, status: 'active', position: 'endorsed', citationCount,
           pendingCitationCount: 0, firstWrittenOn: null, lastWrittenOn: null, undatedCount: 0, needsEvidence: false };
}
function link(id: string, from: string, to: string, kind: IdeaLink['kind'] = 'supports'): IdeaLink {
  return { id, fromIdeaId: from, toIdeaId: to, kind, rationale: '', status: 'accepted', fromStatement: '', toStatement: '' };
}
const label = (d: string) => d.toUpperCase();

describe('buildGraph', () => {
  it('draws each idea and the accepted links, and area hubs only when asked', () => {
    const base = { ideas: [idea('1'), idea('2'), idea('3', 'learning')], links: [link('l', '1', '2')], areaLabel: label };
    expect(buildGraph({ ...base, showAreas: false }).nodes.map(n => n.id)).toEqual(['i:1', 'i:2', 'i:3']);
    const withAreas = buildGraph({ ...base, showAreas: true });
    expect(withAreas.nodes.map(n => n.id).sort()).toEqual(['a:ethics', 'a:learning', 'i:1', 'i:2', 'i:3']);
    expect(withAreas.lines.filter(l => l.kind === 'area')).toHaveLength(3);
  });

  it('pulls ideas that share a meaning closer than other links', () => {
    const g = buildGraph({ ideas: [idea('1', 'markets'), idea('2', 'life'), idea('3')],
                           links: [link('s', '1', '2', 'same_meaning'), link('o', '1', '3', 'supports')],
                           showAreas: false, areaLabel: label });
    const same = g.lines.find(l => l.kind === 'same_meaning')!, other = g.lines.find(l => l.kind === 'supports')!;
    expect(same.length).toBeLessThan(other.length);
  });

  it('draws a Life idea larger than a field idea written as often', () => {
    const g = buildGraph({ ideas: [idea('1', 'markets'), idea('2', 'life')], links: [], showAreas: false, areaLabel: label });
    expect(g.nodes[1].size).toBeGreaterThan(g.nodes[0].size);
  });

  it('draws proposals grey, and never twice', () => {
    const g = buildGraph({ ideas: [idea('1')], links: [], proposedIdeas: [idea('1'), idea('9')],
                           proposedLinks: [link('p', '1', '9', 'contradicts')], showAreas: false, areaLabel: label });
    expect(g.nodes.map(n => [n.id, n.proposed])).toEqual([['i:1', false], ['i:9', true]]);
    expect(g.lines).toEqual([expect.objectContaining({ source: 'i:1', target: 'i:9', proposed: true })]);
  });

  it('leaves out links to ideas that are not drawn', () => {
    expect(buildGraph({ ideas: [idea('1')], links: [link('l', '1', 'hidden')], showAreas: false, areaLabel: label }).lines).toEqual([]);
  });

  it('lights up a node and its direct neighbours only', () => {
    const lines = [{ source: { id: 'a' }, target: { id: 'b' } }, { source: 'b', target: 'c' }];
    expect([...neighbourhood('a', lines)].sort()).toEqual(['a', 'b']);
  });
});

function Where() {
  const at = useLocation();
  return <div data-testid="where">{at.pathname + at.search}</div>;
}

describe('IdeaGraph', () => {
  it('hands the graph to the renderer and opens an idea or Review on click', () => {
    const view = render(
      <MemoryRouter initialEntries={['/ideas']}>
        <Routes><Route path="*" element={<>
          <IdeaGraph ideas={[idea('1')]} links={[]} proposedIdeas={[idea('9')]} showAreas={false} areaLabel={label} />
          <Where />
        </>} /></Routes>
      </MemoryRouter>,
    );
    const g = lib.instance!;
    expect((g.data as { nodes: { id: string }[] }).nodes.map(n => n.id)).toEqual(['i:1', 'i:9']);
    const [accepted, proposed] = (g.data as { nodes: unknown[] }).nodes;
    act(() => g.handlers.onNodeClick(accepted));
    expect(view.getByTestId('where')).toHaveTextContent('/ideas/1');
    act(() => g.handlers.onNodeClick(proposed));
    expect(view.getByTestId('where')).toHaveTextContent('/ideas?view=review');
  });
});

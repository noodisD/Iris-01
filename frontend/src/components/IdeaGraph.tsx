import React from 'react';
import { useNavigate } from 'react-router-dom';
import ForceGraph3D, { type ForceGraph3DInstance } from '3d-force-graph';
import { Vector2 } from 'three';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import type { IdeaDomain, IdeaLink, IdeaSummary } from '@/types/api';

/**
 * The ideas framework as a 3D graph, in the manner of Obsidian's 3D graph.
 *
 * Each idea is a glowing sphere, coloured by its area and sized by how often it
 * was written; a Life idea, a principle the owner states as holding across
 * areas, is drawn larger. Accepted links join ideas. "Same meaning" links are
 * short, so ideas that say one thing in different fields pull together into a
 * cluster, and carry a slow stream of particles. Area hubs are optional, like
 * tags in Obsidian. Proposals still waiting in Review can be shown, dim, so
 * they are never mistaken for what the owner accepted. Drag to rotate, scroll
 * to zoom, hover to read and light up neighbours, click to open.
 */

export const DOMAIN_COLOR: Record<IdeaDomain, string> = {
  philosophy: '#9aa3d4', economics: '#d4a374', markets: '#d48a8a', politics: '#c9a3d4',
  ethics: '#a9c8a3', learning: '#8fc4c9', life: '#f0d68a', other: '#807969',
};
export const LINK_COLOR: Record<IdeaLink['kind'], string> = {
  same_meaning: '#f0d68a', supports: '#a9c8a3', contradicts: '#d48a8a', refines: '#9aa3d4', depends_on: '#d4a374',
};
export const LINK_LABEL: Record<IdeaLink['kind'], string> = {
  same_meaning: 'same meaning', supports: 'supports', contradicts: 'contradicts', refines: 'refines', depends_on: 'depends on',
};
const PROPOSED = '#5c574a';
const AREA_EDGE = '#3a3a2c';

interface Props {
  ideas: IdeaSummary[];
  links: IdeaLink[];
  proposedIdeas?: IdeaSummary[];
  proposedLinks?: IdeaLink[];
  showAreas: boolean;
  areaLabel: (domain: IdeaDomain) => string;
  height?: number;
}

export interface Drawn {
  id: string;
  kind: 'idea' | 'area';
  label: string;
  color: string;
  /** Relative size. */
  size: number;
  proposed: boolean;
  ideaId?: string;
}

export interface Line {
  source: string;
  target: string;
  /** Rest length: shorter pulls tighter. */
  length: number;
  color: string;
  width: number;
  kind: IdeaLink['kind'] | 'area';
  proposed: boolean;
}

/** What to draw: nodes and edges from the framework, areas and proposals as asked. */
export function buildGraph({ ideas, links, proposedIdeas = [], proposedLinks = [], showAreas, areaLabel }: Props) {
  const nodes: Drawn[] = [];
  const lines: Line[] = [];
  const add = (idea: IdeaSummary, proposed: boolean) => nodes.push({
    id: `i:${idea.id}`, kind: 'idea', label: idea.statement,
    color: proposed ? PROPOSED : DOMAIN_COLOR[idea.domain],
    size: (idea.domain === 'life' ? 3 : 1) * (1 + Math.sqrt(Math.max(idea.citationCount, 1))),
    proposed, ideaId: idea.id,
  });
  ideas.forEach(idea => add(idea, false));
  const accepted = new Set(ideas.map(i => i.id));
  proposedIdeas.filter(i => !accepted.has(i.id)).forEach(idea => add(idea, true));
  const drawn = new Set(nodes.map(n => n.id));

  if (showAreas) {
    const shown = [...ideas, ...proposedIdeas].filter(i => drawn.has(`i:${i.id}`));
    for (const area of new Set(shown.map(i => i.domain))) {
      nodes.push({ id: `a:${area}`, kind: 'area', label: areaLabel(area), color: DOMAIN_COLOR[area], size: 5, proposed: false });
    }
    for (const idea of shown) {
      lines.push({ source: `i:${idea.id}`, target: `a:${idea.domain}`, length: 70, color: AREA_EDGE,
                   width: 0, kind: 'area', proposed: false });
    }
  }
  const link = (l: IdeaLink, proposed: boolean) => {
    const source = `i:${l.fromIdeaId}`, target = `i:${l.toIdeaId}`;
    if (!drawn.has(source) || !drawn.has(target)) return;
    const same = l.kind === 'same_meaning';
    lines.push({ source, target, length: same ? 28 : 90, color: proposed ? PROPOSED : LINK_COLOR[l.kind],
                 width: proposed ? 0 : same ? 1.4 : 0.8, kind: l.kind, proposed });
  };
  links.forEach(l => link(l, false));
  proposedLinks.forEach(l => link(l, true));
  return { nodes, lines };
}

/** A node's own id and its direct neighbours': what a hover lights up. */
export function neighbourhood(id: string, lines: { source?: unknown; target?: unknown }[]): Set<string> {
  const idOf = (end: unknown) => (typeof end === 'object' && end ? (end as { id: string }).id : String(end));
  const out = new Set([id]);
  for (const l of lines) {
    const s = idOf(l.source), t = idOf(l.target);
    if (s === id) out.add(t);
    if (t === id) out.add(s);
  }
  return out;
}

function tooltip(n: Drawn): string {
  const box = document.createElement('div');
  box.textContent = n.kind === 'area' ? n.label : n.proposed ? `${n.label} (proposed)` : n.label;
  Object.assign(box.style, {
    maxWidth: '360px', padding: '8px 10px', borderRadius: '8px', background: 'rgba(20,20,15,0.92)',
    border: '1px solid #2a2a1f', color: '#e9e3d3', font: '13px/1.4 Geist, system-ui, sans-serif',
  });
  return box.outerHTML;
}

export function IdeaGraph(props: Props) {
  const nav = useNavigate();
  const holder = React.useRef<HTMLDivElement>(null);
  const graph = React.useRef<ForceGraph3DInstance | null>(null);
  const lit = React.useRef<Set<string> | null>(null);
  const fitted = React.useRef(false);
  const navRef = React.useRef(nav);
  navRef.current = nav;
  const height = props.height ?? 640;

  // Callers rebuild their lists on every render, so identity says nothing. Key
  // the data on the graph's shape instead, or the layout would restart each time.
  const built = buildGraph(props);
  const shape = JSON.stringify([built.nodes.map(n => [n.id, n.size, n.proposed, n.color]),
                                built.lines.map(l => [l.source, l.target, l.kind, l.proposed])]);
  const builtRef = React.useRef(built);
  builtRef.current = built;

  React.useEffect(() => {
    const el = holder.current;
    if (!el) return;
    const g = new ForceGraph3D(el, { controlType: 'orbit' })
      .backgroundColor('#000000')
      .showNavInfo(false)
      .nodeRelSize(6)
      .nodeResolution(20)
      .nodeOpacity(0.92)
      .linkOpacity(0.45)
      .nodeLabel(node => tooltip(node as unknown as Drawn))
      .nodeVal(node => (node as unknown as Drawn).size)
      .nodeColor(node => {
        const n = node as unknown as Drawn;
        return !lit.current || lit.current.has(n.id) ? n.color : '#24231c';
      })
      .linkColor(link => {
        const l = link as unknown as Line & { source: { id: string }; target: { id: string } };
        const on = !lit.current || (lit.current.has(l.source.id) && lit.current.has(l.target.id));
        return on ? l.color : '#1c1b15';
      })
      .linkWidth(link => (link as unknown as Line).width)
      .linkDirectionalParticles(link => {
        const l = link as unknown as Line;
        return l.kind === 'same_meaning' && !l.proposed ? 2 : 0;
      })
      .linkDirectionalParticleWidth(1.6)
      .linkDirectionalParticleSpeed(0.004)
      .linkDirectionalParticleColor(() => '#f0d68a')
      .onNodeHover(node => {
        el.style.cursor = node ? 'pointer' : 'grab';
        lit.current = node ? neighbourhood(String(node.id), g.graphData().links) : null;
        g.nodeColor(g.nodeColor()).linkColor(g.linkColor());
      })
      .onNodeClick(node => {
        const n = node as unknown as Drawn;
        if (n.kind !== 'idea') return;
        navRef.current(n.proposed ? '/ideas?view=review' : `/ideas/${n.ideaId}`);
      })
      // Settle within three seconds, so the view fits itself promptly.
      .cooldownTime(3000)
      .onEngineStop(() => {
        if (!fitted.current) { fitted.current = true; g.zoomToFit(600, 40); }
      });
    // The soft glow of Obsidian's 3D graph. Optional: without WebGL post-processing
    // the spheres are drawn plainly.
    try {
      g.postProcessingComposer().addPass(new UnrealBloomPass(new Vector2(el.clientWidth || 900, height), 0.9, 0.5, 0.3));
    } catch { /* no glow */ }
    const linkForce = g.d3Force('link') as unknown as { distance?: (fn: (l: Line) => number) => void } | undefined;
    linkForce?.distance?.(l => l.length);
    graph.current = g;
    const resize = () => { g.width(el.clientWidth || 900).height(height); };
    resize();
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    ro?.observe(el);
    return () => { ro?.disconnect(); g._destructor(); graph.current = null; };
  }, [height]);

  React.useEffect(() => {
    // The library adds positions to the objects it is given, so hand it copies.
    graph.current?.graphData({
      nodes: builtRef.current.nodes.map(n => ({ ...n })),
      links: builtRef.current.lines.map(l => ({ ...l })),
    });
    fitted.current = false;
  }, [shape, height]);

  const kinds = Object.keys(LINK_COLOR) as IdeaLink['kind'][];
  return (
    <div className="col" style={{ gap: 10 }}>
      <div ref={holder} role="img" aria-label="Ideas graph"
        style={{ height, borderRadius: 10, overflow: 'hidden', border: '1px solid var(--line-soft)', background: '#000000' }} />
      <div className="row" style={{ gap: 16, flexWrap: 'wrap', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)',
                                    letterSpacing: '0.08em', textTransform: 'uppercase' }}>
        {kinds.map(kind => (
          <span key={kind} className="row" style={{ gap: 6, alignItems: 'center' }}>
            <span style={{ width: 14, height: 2, background: LINK_COLOR[kind] }} />{LINK_LABEL[kind]}
          </span>
        ))}
        <span className="row" style={{ gap: 6, alignItems: 'center' }}>
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: DOMAIN_COLOR.life }} />life
        </span>
        <span>grey · proposed, waiting in review</span>
        <span>drag to turn · scroll to zoom · hover to read</span>
      </div>
    </div>
  );
}

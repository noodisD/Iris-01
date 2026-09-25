import React from 'react';
import { useNavigate } from 'react-router-dom';
import { fit, neighbourhood, seed, tick, type GraphEdge, type GraphNode } from '@/lib/forceGraph';
import type { IdeaDomain, IdeaLink, IdeaSummary } from '@/types/api';

/**
 * The ideas framework as a graph, in the manner of Obsidian's graph view.
 *
 * Each idea is a dot, coloured by its area and sized by how often it was
 * written. Accepted links join ideas, styled by kind. Each area can be drawn as
 * a hub its ideas hang from, like tags in Obsidian. Proposals still waiting in
 * Review can be shown too, hollow and dashed, so they are never mistaken for
 * what the owner accepted. Drag a dot, drag the background to pan, scroll to
 * zoom; hovering lights up a dot's neighbours and shows its statement.
 */

export const DOMAIN_COLOR: Record<IdeaDomain, string> = {
  philosophy: 'var(--indigo)', economics: 'var(--amber)', markets: 'var(--rose)',
  politics: '#c9a3d4', ethics: 'var(--sage)', learning: '#8fc4c9', other: 'var(--ink-3)',
};
export const LINK_COLOR: Record<IdeaLink['kind'], string> = {
  supports: 'var(--sage)', contradicts: 'var(--rose)', refines: 'var(--indigo)', depends_on: 'var(--amber)',
};
const LINK_LABEL: Record<IdeaLink['kind'], string> = {
  supports: 'supports', contradicts: 'contradicts', refines: 'refines', depends_on: 'depends on',
};

interface Props {
  ideas: IdeaSummary[];
  links: IdeaLink[];
  proposedIdeas?: IdeaSummary[];
  proposedLinks?: IdeaLink[];
  showAreas: boolean;
  areaLabel: (domain: IdeaDomain) => string;
}

interface Drawn {
  id: string;
  kind: 'idea' | 'area';
  label: string;
  color: string;
  r: number;
  proposed: boolean;
  ideaId?: string;
}

interface Line extends GraphEdge {
  color: string;
  dashed: boolean;
  width: number;
  title?: string;
}

function short(text: string, n = 60): string {
  return text.length > n ? `${text.slice(0, n - 1)}…` : text;
}

/** What to draw: nodes and edges from the framework, areas and proposals as asked. */
export function buildGraph({ ideas, links, proposedIdeas = [], proposedLinks = [], showAreas, areaLabel }: Props) {
  const nodes: Drawn[] = [];
  const lines: Line[] = [];
  const add = (idea: IdeaSummary, proposed: boolean) => nodes.push({
    id: `i:${idea.id}`, kind: 'idea', label: idea.statement, color: DOMAIN_COLOR[idea.domain],
    r: 4 + 2.2 * Math.sqrt(Math.max(idea.citationCount, 1)), proposed, ideaId: idea.id,
  });
  ideas.forEach(idea => add(idea, false));
  const accepted = new Set(ideas.map(i => i.id));
  proposedIdeas.filter(i => !accepted.has(i.id)).forEach(idea => add(idea, true));
  const drawn = new Set(nodes.map(n => n.id));

  if (showAreas) {
    const areas = [...new Set([...ideas, ...proposedIdeas].filter(i => drawn.has(`i:${i.id}`)).map(i => i.domain))];
    for (const area of areas) {
      nodes.push({ id: `a:${area}`, kind: 'area', label: areaLabel(area), color: DOMAIN_COLOR[area], r: 11, proposed: false });
    }
    for (const idea of [...ideas, ...proposedIdeas]) {
      if (drawn.has(`i:${idea.id}`)) {
        lines.push({ source: `i:${idea.id}`, target: `a:${idea.domain}`, length: 80,
                     color: 'var(--line)', dashed: false, width: 1 });
      }
    }
  }
  const link = (l: IdeaLink, proposed: boolean) => {
    const source = `i:${l.fromIdeaId}`, target = `i:${l.toIdeaId}`;
    if (!drawn.has(source) || !drawn.has(target)) return;
    lines.push({ source, target, length: 140, color: LINK_COLOR[l.kind], dashed: proposed, width: 1.6,
                 title: `${LINK_LABEL[l.kind]}${proposed ? ' (proposed)' : ''}` });
  };
  links.forEach(l => link(l, false));
  proposedLinks.forEach(l => link(l, true));
  return { nodes, lines };
}

const HEIGHT = 620;
/** Zoomed in this far, every statement is labelled; below it, only on hover. */
const LABEL_ZOOM = 1.8;

export function IdeaGraph(props: Props) {
  const nav = useNavigate();
  // Callers rebuild their lists on every render, so identity says nothing. Key
  // the layout on the graph's shape instead, or it would never come to rest.
  const built = buildGraph(props);
  const shape = JSON.stringify([built.nodes.map(n => [n.id, n.r, n.proposed, n.label]),
                                built.lines.map(l => [l.source, l.target, l.dashed, l.color])]);
  const { nodes, lines } = React.useMemo(() => built, [shape]);

  const positions = React.useRef(new Map<string, GraphNode>());
  const [, setFrame] = React.useState(0);
  const [view, setView] = React.useState({ x: 0, y: 0, k: 1 });
  const [hover, setHover] = React.useState<string | null>(null);
  const [width, setWidth] = React.useState(900);
  const svg = React.useRef<SVGSVGElement>(null);
  const drag = React.useRef<{ id: string | null; startX: number; startY: number; moved: boolean; view: typeof view } | null>(null);
  const running = React.useRef(false);
  // Until the owner pans or zooms, each settled layout is fitted to the view.
  const placedByOwner = React.useRef(false);

  // Keep positions across data changes; new nodes start on the spiral.
  const sim = React.useMemo(() => {
    const fresh = seed(nodes.map(n => n.id));
    return fresh.map(n => positions.current.get(n.id) ?? n);
  }, [nodes]);
  React.useEffect(() => { positions.current = new Map(sim.map(n => [n.id, n])); }, [sim]);

  const heat = React.useCallback(() => {
    if (running.current) return;
    running.current = true;
    const raf = window.requestAnimationFrame ?? ((f: FrameRequestCallback) => window.setTimeout(() => f(0), 16));
    let steps = 0;
    const loop = () => {
      let energy = 0;
      for (let i = 0; i < 3; i++) { energy = tick(sim, lines); steps++; }
      setFrame(f => f + 1);
      if ((energy > 0.02 || drag.current?.id) && steps < 900) raf(loop);
      else {
        running.current = false;
        const w = svg.current?.getBoundingClientRect().width || 900;
        if (!placedByOwner.current) setView(fit(sim, w, HEIGHT, 90, LABEL_ZOOM - 0.3));
      }
    };
    raf(loop);
  }, [sim, lines]);
  React.useEffect(() => { heat(); }, [heat]);

  React.useEffect(() => {
    const el = svg.current;
    if (!el) return;
    const measure = () => setWidth(el.getBoundingClientRect().width || 900);
    measure();
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    ro?.observe(el);
    return () => ro?.disconnect();
  }, []);

  const toGraph = (clientX: number, clientY: number) => {
    const rect = svg.current!.getBoundingClientRect();
    return { x: (clientX - rect.left - width / 2 - view.x) / view.k, y: (clientY - rect.top - HEIGHT / 2 - view.y) / view.k };
  };

  const onPointerDown = (event: React.PointerEvent, id: string | null) => {
    event.stopPropagation();
    (event.target as Element).setPointerCapture?.(event.pointerId);
    drag.current = { id, startX: event.clientX, startY: event.clientY, moved: false, view };
    if (id) { const n = positions.current.get(id); if (n) n.pinned = true; heat(); }
  };
  const onPointerMove = (event: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    if (Math.hypot(event.clientX - d.startX, event.clientY - d.startY) > 3) d.moved = true;
    if (d.id) {
      const n = positions.current.get(d.id);
      if (n) { const p = toGraph(event.clientX, event.clientY); n.x = p.x; n.y = p.y; setFrame(f => f + 1); }
    } else {
      placedByOwner.current = true;
      setView({ ...d.view, x: d.view.x + event.clientX - d.startX, y: d.view.y + event.clientY - d.startY });
    }
  };
  const onPointerUp = (node?: Drawn) => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (d.id) { const n = positions.current.get(d.id); if (n) n.pinned = false; heat(); }
    if (node?.kind === 'idea' && !d.moved) nav(node.proposed ? '/ideas?view=review' : `/ideas/${node.ideaId}`);
  };
  const onWheel = (event: React.WheelEvent) => {
    placedByOwner.current = true;
    const k = Math.min(4, Math.max(0.3, view.k * Math.exp(-event.deltaY * 0.0015)));
    const rect = svg.current!.getBoundingClientRect();
    const cx = event.clientX - rect.left - width / 2, cy = event.clientY - rect.top - HEIGHT / 2;
    // Zoom about the cursor: the point under it stays put.
    setView({ k, x: cx - ((cx - view.x) * k) / view.k, y: cy - ((cy - view.y) * k) / view.k });
  };

  const lit = hover ? neighbourhood(hover, lines) : null;
  const at = (id: string) => positions.current.get(id) ?? { x: 0, y: 0 };
  const showLabel = (n: Drawn) => n.kind === 'area' || view.k >= LABEL_ZOOM || (lit?.has(n.id) ?? false);

  return (
    <div className="col" style={{ gap: 10 }}>
      <svg ref={svg} role="img" aria-label="Ideas graph" width="100%" height={HEIGHT}
        style={{ background: 'var(--bg-1)', border: '1px solid var(--line-soft)', borderRadius: 10,
                 touchAction: 'none', cursor: drag.current && !drag.current.id ? 'grabbing' : 'grab', userSelect: 'none' }}
        onPointerDown={event => onPointerDown(event, null)} onPointerMove={onPointerMove}
        onPointerUp={() => onPointerUp()} onPointerLeave={() => onPointerUp()} onWheel={onWheel}>
        <g transform={`translate(${width / 2 + view.x} ${HEIGHT / 2 + view.y}) scale(${view.k})`}>
          {lines.map((l, i) => {
            const a = at(l.source), b = at(l.target);
            const on = !lit || (lit.has(l.source) && lit.has(l.target));
            return (
              <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={l.color} strokeWidth={l.width / view.k}
                strokeDasharray={l.dashed ? `${4 / view.k} ${3 / view.k}` : undefined} opacity={on ? 0.9 : 0.12}>
                {l.title && <title>{l.title}</title>}
              </line>
            );
          })}
          {nodes.map(n => {
            const p = at(n.id);
            const on = !lit || lit.has(n.id);
            return (
              <g key={n.id} transform={`translate(${p.x} ${p.y})`} opacity={on ? 1 : 0.18} style={{ cursor: 'pointer' }}
                role="button" aria-label={n.kind === 'area' ? `Area: ${n.label}` : `${n.proposed ? 'Proposed idea' : 'Idea'}: ${n.label}`}
                onPointerDown={event => onPointerDown(event, n.id)} onPointerUp={event => { event.stopPropagation(); onPointerUp(n); }}
                onPointerEnter={() => setHover(n.id)} onPointerLeave={() => setHover(h => (h === n.id ? null : h))}>
                {n.kind === 'area'
                  ? <circle r={n.r} fill="var(--bg-1)" stroke={n.color} strokeWidth={2} />
                  : <circle r={n.r} fill={n.proposed ? 'var(--bg-1)' : n.color} stroke={n.color}
                      strokeWidth={n.proposed ? 1.5 : 0} strokeDasharray={n.proposed ? '3 2' : undefined} />}
                {showLabel(n) && (
                  <text y={n.r + 12 / view.k} textAnchor="middle" fontSize={(n.kind === 'area' ? 12 : 11) / view.k}
                    fill={n.kind === 'area' ? n.color : 'var(--ink-2)'}
                    fontFamily={n.kind === 'area' ? 'var(--mono)' : 'var(--sans)'}
                    style={{ pointerEvents: 'none', textTransform: n.kind === 'area' ? 'uppercase' : undefined }}>
                    {n.kind === 'area' ? n.label : short(n.label, hover === n.id ? 90 : 40)}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>
      <div className="row" style={{ gap: 16, flexWrap: 'wrap', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)',
                                    letterSpacing: '0.08em', textTransform: 'uppercase' }}>
        {(Object.keys(LINK_COLOR) as IdeaLink['kind'][]).map(kind => (
          <span key={kind} className="row" style={{ gap: 6, alignItems: 'center' }}>
            <span style={{ width: 14, height: 2, background: LINK_COLOR[kind] }} />{LINK_LABEL[kind]}
          </span>
        ))}
        <span>dashed · proposed, waiting in review</span>
        <span>drag · scroll to zoom · hover to read</span>
      </div>
    </div>
  );
}

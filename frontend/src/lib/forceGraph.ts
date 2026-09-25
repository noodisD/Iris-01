/**
 * A small force-directed layout, in the manner of Obsidian's graph view: nodes
 * push each other apart, edges pull their ends together, and a weak pull toward
 * the centre keeps everything on screen. Pure and deterministic, so it can be
 * tested without a browser; the component runs `tick` once per frame.
 */

export interface GraphNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** Held in place while the owner drags it. */
  pinned?: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  /** Rest length; shorter pulls tighter. */
  length?: number;
}

export const FORCES = { charge: 4200, spring: 0.05, length: 110, gravity: 0.006, damping: 0.8 };

/** Starting positions on a golden-angle spiral: spread out, and the same every time. */
export function seed(ids: string[]): GraphNode[] {
  const golden = Math.PI * (3 - Math.sqrt(5));
  return ids.map((id, i) => {
    const r = 28 * Math.sqrt(i + 1);
    return { id, x: r * Math.cos(i * golden), y: r * Math.sin(i * golden), vx: 0, vy: 0 };
  });
}

/** One step of the simulation, in place. Returns the kinetic energy left. */
export function tick(nodes: GraphNode[], edges: GraphEdge[], forces = FORCES): number {
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j];
      let dx = b.x - a.x, dy = b.y - a.y;
      if (dx === 0 && dy === 0) { dx = 0.01 * (j - i); dy = 0.01; }
      const d2 = Math.max(dx * dx + dy * dy, 25);
      const d = Math.sqrt(d2);
      const f = forces.charge / d2;
      const fx = (dx / d) * f, fy = (dy / d) * f;
      a.vx -= fx; a.vy -= fy;
      b.vx += fx; b.vy += fy;
    }
  }
  const byId = new Map(nodes.map(n => [n.id, n]));
  for (const e of edges) {
    const a = byId.get(e.source), b = byId.get(e.target);
    if (!a || !b) continue;
    const dx = b.x - a.x, dy = b.y - a.y;
    const d = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01);
    const f = (d - (e.length ?? forces.length)) * forces.spring;
    const fx = (dx / d) * f, fy = (dy / d) * f;
    a.vx += fx; a.vy += fy;
    b.vx -= fx; b.vy -= fy;
  }
  let energy = 0;
  for (const n of nodes) {
    if (n.pinned) { n.vx = 0; n.vy = 0; continue; }
    n.vx = (n.vx - n.x * forces.gravity) * forces.damping;
    n.vy = (n.vy - n.y * forces.gravity) * forces.damping;
    n.x += n.vx;
    n.y += n.vy;
    energy += n.vx * n.vx + n.vy * n.vy;
  }
  return energy;
}

/** Ids joined to `id` by an edge, and `id` itself: what a hover lights up. */
export function neighbourhood(id: string, edges: GraphEdge[]): Set<string> {
  const out = new Set([id]);
  for (const e of edges) {
    if (e.source === id) out.add(e.target);
    if (e.target === id) out.add(e.source);
  }
  return out;
}

/**
 * The zoom and offset that fit every node in a width × height view, with a
 * margin, and never zoomed in past `maxScale`: a small graph is shown at a
 * readable size, not blown up.
 */
export function fit(nodes: { x: number; y: number }[], width: number, height: number,
                    margin = 60, maxScale = 2.2): { x: number; y: number; k: number } {
  if (nodes.length === 0) return { x: 0, y: 0, k: 1 };
  const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const k = Math.min(maxScale, (width - 2 * margin) / Math.max(maxX - minX, 1),
                     (height - 2 * margin) / Math.max(maxY - minY, 1));
  return { x: -((minX + maxX) / 2) * k, y: -((minY + maxY) / 2) * k, k };
}

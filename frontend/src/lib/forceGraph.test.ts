import { describe, expect, it } from 'vitest';
import { fit, neighbourhood, seed, tick } from './forceGraph';

function settle(ids: string[], edges: { source: string; target: string }[], steps = 400) {
  const nodes = seed(ids);
  for (let i = 0; i < steps; i++) tick(nodes, edges);
  return new Map(nodes.map(n => [n.id, n]));
}
const dist = (a: { x: number; y: number }, b: { x: number; y: number }) => Math.hypot(a.x - b.x, a.y - b.y);

describe('force layout', () => {
  it('starts the same way every time, with no two nodes on top of each other', () => {
    const a = seed(['p', 'q', 'r']), b = seed(['p', 'q', 'r']);
    expect(a).toEqual(b);
    expect(dist(a[0], a[1])).toBeGreaterThan(5);
  });

  it('pulls linked nodes closer than unlinked ones', () => {
    const at = settle(['a', 'b', 'c', 'd'], [{ source: 'a', target: 'b' }]);
    expect(dist(at.get('a')!, at.get('b')!)).toBeLessThan(dist(at.get('c')!, at.get('d')!));
  });

  it('comes to rest', () => {
    const nodes = seed(['a', 'b', 'c']);
    let energy = Infinity;
    for (let i = 0; i < 500; i++) energy = tick(nodes, [{ source: 'a', target: 'b' }]);
    expect(energy).toBeLessThan(0.01);
  });

  it('leaves a pinned node where the owner put it', () => {
    const nodes = seed(['a', 'b']);
    nodes[0].pinned = true; nodes[0].x = 50; nodes[0].y = -20;
    for (let i = 0; i < 50; i++) tick(nodes, []);
    expect([nodes[0].x, nodes[0].y]).toEqual([50, -20]);
  });

  it('ignores edges to nodes that are not drawn', () => {
    const nodes = seed(['a']);
    expect(() => tick(nodes, [{ source: 'a', target: 'gone' }])).not.toThrow();
  });

  it('lights up a node and its direct neighbours only', () => {
    const edges = [{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }];
    expect([...neighbourhood('a', edges)].sort()).toEqual(['a', 'b']);
  });

  it('fits the graph into the view, centred, without blowing a small one up', () => {
    const v = fit([{ x: -100, y: 0 }, { x: 100, y: 50 }], 1000, 600);
    expect(v.k).toBeCloseTo(2.2);
    expect(v.x).toBeCloseTo(0);
    expect(v.y).toBeCloseTo(-25 * 2.2);
    const wide = fit([{ x: -1000, y: 0 }, { x: 1000, y: 0 }], 1000, 600);
    expect(wide.k).toBeCloseTo(880 / 2000);
  });
});

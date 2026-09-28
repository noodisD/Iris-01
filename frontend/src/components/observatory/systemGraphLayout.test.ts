import { describe, expect, it } from 'vitest';
import {
  type GraphCard,
  type GraphPlacement,
  layoutComponent,
  layoutOverview,
  routeConnection,
} from './systemGraphLayout';

const BASELINE = [
  'web', 'android', 'http', 'voice', 'chat', 'import', 'sensors', 'ideas', 'insights',
  'engine', 'admission', 'queue', 'pipeline', 'llm', 'db', 'system',
];

const OVERVIEW_CELLS: Record<string, { column: number; row: number }> = {
  web: { column: 0, row: 1 },
  android: { column: 0, row: 3 },
  http: { column: 1, row: 1 },
  voice: { column: 2, row: 0 },
  chat: { column: 2, row: 1 },
  import: { column: 2, row: 2 },
  sensors: { column: 2, row: 3 },
  ideas: { column: 2, row: 4 },
  insights: { column: 2, row: 5 },
  engine: { column: 3, row: 0 },
  admission: { column: 3, row: 1 },
  queue: { column: 3, row: 2 },
  pipeline: { column: 3, row: 3 },
  llm: { column: 4, row: 1 },
  db: { column: 4, row: 3 },
  system: { column: 4, row: 5 },
};

function overlaps(left: GraphCard, right: GraphCard): boolean {
  return left.x < right.x + right.width
    && left.x + left.width > right.x
    && left.y < right.y + right.height
    && left.y + left.height > right.y;
}

function assertPacked(placement: GraphPlacement) {
  placement.cards.forEach((card, index) => {
    expect(card.x).toBeGreaterThanOrEqual(0);
    expect(card.y).toBeGreaterThanOrEqual(0);
    expect(card.x + card.width).toBeLessThanOrEqual(placement.width);
    expect(card.y + card.height).toBeLessThanOrEqual(placement.height);
    placement.cards.slice(index + 1).forEach(other => {
      expect(overlaps(card, other), `${card.id} overlaps ${other.id}`).toBe(false);
    });
  });
}

function moduleDepth(card: GraphCard): number {
  return (card.x - 200) / 288;
}

function backEdges(ids: readonly string[], structure: readonly { source: string; target: string }[]): Set<string> {
  const present = new Set(ids);
  const outgoing = new Map<string, string[]>();
  for (const edge of structure) {
    if (!present.has(edge.source) || !present.has(edge.target) || edge.source === edge.target) continue;
    const targets = outgoing.get(edge.source) ?? [];
    if (!targets.includes(edge.target)) targets.push(edge.target);
    outgoing.set(edge.source, targets);
  }
  for (const targets of outgoing.values()) targets.sort((a, b) => a.localeCompare(b));
  const color = new Map<string, number>();
  const ignored = new Set<string>();
  const visit = (id: string) => {
    color.set(id, 1);
    for (const target of outgoing.get(id) ?? []) {
      const state = color.get(target) ?? 0;
      if (state === 1) ignored.add(`${id}|${target}`);
      else if (state === 0) visit(target);
    }
    color.set(id, 2);
  };
  for (const id of ids) {
    if ((outgoing.has(id) || structure.some(edge => edge.target === id)) && (color.get(id) ?? 0) === 0) visit(id);
  }
  return ignored;
}

function assertForward(ids: readonly string[], structure: readonly { source: string; target: string }[], placement: GraphPlacement) {
  const ignored = backEdges(ids, structure);
  const byId = new Map(placement.cards.map(card => [card.id, card]));
  for (const edge of structure) {
    if (ignored.has(`${edge.source}|${edge.target}`)) continue;
    const source = byId.get(`module:${edge.source}`);
    const target = byId.get(`module:${edge.target}`);
    expect(source, edge.source).toBeTruthy();
    expect(target, edge.target).toBeTruthy();
    expect(moduleDepth(target!)).toBeGreaterThan(moduleDepth(source!));
  }
}

function segmentHits(start: { x: number; y: number }, end: { x: number; y: number }, card: GraphCard): boolean {
  const left = card.x - 4;
  const right = card.x + card.width + 4;
  const top = card.y - 4;
  const bottom = card.y + card.height + 4;
  if (start.x === end.x) {
    const y1 = Math.min(start.y, end.y);
    const y2 = Math.max(start.y, end.y);
    return start.x >= left && start.x <= right && y2 >= top && y1 <= bottom;
  }
  if (start.y === end.y) {
    const x1 = Math.min(start.x, end.x);
    const x2 = Math.max(start.x, end.x);
    return start.y >= top && start.y <= bottom && x2 >= left && x1 <= right;
  }
  return true;
}

function assertRoutes(placement: GraphPlacement, pairs: [GraphCard, GraphCard][]) {
  const failures: string[] = [];
  for (const [source, target] of pairs) {
    for (let slot = 0; slot < 5; slot += 1) {
      const points = routeConnection(source, target, placement, slot);
      const label = `${source.id} to ${target.id} slot ${slot}`;
      if (points.length < 2) {
        failures.push(`${label} has no segment`);
        continue;
      }
      for (let index = 1; index < points.length; index += 1) {
        const previous = points[index - 1];
        const point = points[index];
        if (previous.x !== point.x && previous.y !== point.y) failures.push(`${label} is diagonal`);
      }
      const start = points[0];
      if (start.x !== source.x + source.width || start.y !== source.y + source.height / 2) {
        failures.push(`${label} misses the source port`);
      }
      const end = points[points.length - 1];
      const before = points[points.length - 2];
      if (end.x !== target.x || end.y !== target.y + target.height / 2) failures.push(`${label} misses the target port`);
      if (!(end.x > before.x && end.y === before.y)) failures.push(`${label} does not finish rightward`);
      for (const card of placement.cards) {
        if (card.id === source.id || card.id === target.id) continue;
        for (let index = 1; index < points.length; index += 1) {
          if (segmentHits(points[index - 1], points[index], card)) {
            failures.push(`${label} crosses ${card.id}`);
            break;
          }
        }
      }
      if (failures.length > 12) break;
    }
    if (failures.length > 12) break;
  }
  expect(failures).toEqual([]);
}

function componentPairs(placement: GraphPlacement): [GraphCard, GraphCard][] {
  const sources = placement.cards.filter(card => card.id.startsWith('module:') || card.id.startsWith('incoming:'));
  const targets = placement.cards.filter(card => card.id.startsWith('module:') || card.id.startsWith('outgoing:'));
  return sources.flatMap(source => targets.filter(target => target.id !== source.id).map(target => [source, target] as [GraphCard, GraphCard]));
}

describe('system map layout', () => {
  it('places the architecture overview without overlap', () => {
    const placement = layoutOverview([...BASELINE, 'alpha', 'zeta']);
    assertPacked(placement);
    expect(placement.width).toBe(1120);
    expect(placement.height).toBe(568 + 128);
    for (const id of BASELINE) {
      const card = placement.cards.find(item => item.id === `component:${id}`);
      const cell = OVERVIEW_CELLS[id];
      expect(card?.column).toBe(cell.column);
      expect(card?.row).toBe(cell.row);
      expect(card?.x).toBe(24 + cell.column * 224);
      expect(card?.y).toBe(40 + cell.row * 88);
    }
    const extras = ['alpha', 'zeta'].map(id => placement.cards.find(card => card.id === `component:${id}`));
    expect(extras.map(card => card?.row)).toEqual([6, 6]);
    expect(extras.map(card => card?.y)).toEqual([608, 608]);
    expect(placement.headings.some(heading => heading.label === 'Other components' && heading.y === 596)).toBe(true);
    const pairs = placement.cards.flatMap((source, index) => (
      placement.cards.slice(index + 1).flatMap(target => [[source, target], [target, source]] as [GraphCard, GraphCard][])
    ));
    assertRoutes(placement, pairs);
  });

  it('layers declared component structure and keeps routes in the gutters', () => {
    const chatIds = [
      'chat.turn', 'chat.begin_turn', 'chat.context', 'chat.stream_reply', 'chat.retrieval',
      'chat.earlier_conversations', 'chat.habits_context', 'chat.reflections_context',
      'chat.approved_context', 'chat.narrative',
    ];
    const chatStructure = [
      ['chat.turn', 'chat.begin_turn'],
      ['chat.begin_turn', 'chat.context'],
      ['chat.context', 'chat.retrieval'],
      ['chat.context', 'chat.earlier_conversations'],
      ['chat.context', 'chat.habits_context'],
      ['chat.context', 'chat.reflections_context'],
      ['chat.context', 'chat.approved_context'],
      ['chat.context', 'chat.narrative'],
      ['chat.begin_turn', 'chat.stream_reply'],
    ].map(([source, target]) => ({ source, target }));
    const chat = layoutComponent({
      moduleIds: chatIds,
      structure: chatStructure,
      incoming: ['http', 'voice'],
      outgoing: ['llm', 'admission'],
      layoutWidth: 1440,
    });
    assertPacked(chat);
    expect(moduleDepth(chat.cards.find(card => card.id === 'module:chat.turn')!)).toBe(0);
    expect(moduleDepth(chat.cards.find(card => card.id === 'module:chat.begin_turn')!)).toBe(1);
    expect(moduleDepth(chat.cards.find(card => card.id === 'module:chat.context')!)).toBe(2);
    expect(moduleDepth(chat.cards.find(card => card.id === 'module:chat.stream_reply')!)).toBe(2);
    for (const id of ['chat.retrieval', 'chat.earlier_conversations', 'chat.habits_context', 'chat.reflections_context', 'chat.approved_context', 'chat.narrative']) {
      expect(moduleDepth(chat.cards.find(card => card.id === `module:${id}`)!)).toBe(3);
    }
    assertForward(chatIds, chatStructure, chat);

    const admissionIds = [
      'admission.collect', 'admission.admit', 'admission.coverage', 'admission.enablement',
      'admission.confidence', 'admission.conflict', 'admission.rank', 'admission.select',
    ];
    const admissionStructure = [
      ['admission.admit', 'admission.coverage'],
      ['admission.admit', 'admission.enablement'],
      ['admission.admit', 'admission.confidence'],
      ['admission.admit', 'admission.conflict'],
      ['admission.admit', 'admission.rank'],
      ['admission.collect', 'admission.coverage'],
      ['admission.coverage', 'admission.enablement'],
      ['admission.enablement', 'admission.confidence'],
      ['admission.confidence', 'admission.conflict'],
      ['admission.conflict', 'admission.rank'],
      ['admission.rank', 'admission.select'],
    ].map(([source, target]) => ({ source, target }));
    const admission = layoutComponent({
      moduleIds: admissionIds,
      structure: admissionStructure,
      incoming: ['chat'],
      outgoing: ['engine', 'chat'],
      layoutWidth: 1440,
    });
    assertPacked(admission);
    expect(moduleDepth(admission.cards.find(card => card.id === 'module:admission.collect')!)).toBe(0);
    expect(moduleDepth(admission.cards.find(card => card.id === 'module:admission.admit')!)).toBe(0);
    expect(moduleDepth(admission.cards.find(card => card.id === 'module:admission.coverage')!)).toBe(1);
    expect(moduleDepth(admission.cards.find(card => card.id === 'module:admission.enablement')!)).toBe(2);
    expect(moduleDepth(admission.cards.find(card => card.id === 'module:admission.confidence')!)).toBe(3);
    expect(moduleDepth(admission.cards.find(card => card.id === 'module:admission.conflict')!)).toBe(4);
    expect(moduleDepth(admission.cards.find(card => card.id === 'module:admission.rank')!)).toBe(5);
    expect(moduleDepth(admission.cards.find(card => card.id === 'module:admission.select')!)).toBe(6);
    assertForward(admissionIds, admissionStructure, admission);

    const cycle = layoutComponent({
      moduleIds: ['a', 'b', 'c'],
      structure: [
        { source: 'a', target: 'b' },
        { source: 'b', target: 'c' },
        { source: 'c', target: 'a' },
      ],
      incoming: [],
      outgoing: [],
      layoutWidth: 1200,
    });
    assertPacked(cycle);
    expect(moduleDepth(cycle.cards.find(card => card.id === 'module:a')!)).toBe(0);
    expect(moduleDepth(cycle.cards.find(card => card.id === 'module:b')!)).toBe(1);
    expect(moduleDepth(cycle.cards.find(card => card.id === 'module:c')!)).toBe(2);
    assertForward(['a', 'b', 'c'], [
      { source: 'a', target: 'b' },
      { source: 'b', target: 'c' },
      { source: 'c', target: 'a' },
    ], cycle);

    const narrowIds = Array.from({ length: 100 }, (_, index) => `m${String(index).padStart(3, '0')}`);
    const narrow = layoutComponent({
      moduleIds: narrowIds,
      structure: [],
      incoming: ['in-a', 'in-b'],
      outgoing: ['out-a', 'out-b', 'out-c', 'out-d', 'out-e', 'out-f', 'out-g'],
      layoutWidth: 390,
    });
    const wide = layoutComponent({
      moduleIds: narrowIds,
      structure: [],
      incoming: ['in-a', 'in-b'],
      outgoing: ['out-a', 'out-b', 'out-c', 'out-d', 'out-e', 'out-f', 'out-g'],
      layoutWidth: 1648,
    });
    assertPacked(narrow);
    assertPacked(wide);
    expect(new Set(narrow.cards.filter(card => card.id.startsWith('module:')).map(card => card.column)).size).toBe(1);
    expect(new Set(wide.cards.filter(card => card.id.startsWith('module:')).map(card => card.x)).size).toBe(4);
    assertForward(narrowIds, [], narrow);

    assertRoutes(chat, componentPairs(chat));
    assertRoutes(admission, componentPairs(admission));
    assertRoutes(cycle, componentPairs(cycle));
    assertRoutes(narrow, componentPairs(narrow));
    assertRoutes(wide, componentPairs(wide));
  });
});

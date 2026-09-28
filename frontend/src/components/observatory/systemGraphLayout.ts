/**
 * Geometry for the Observatory system map. No React and no data aggregation:
 * callers decide which cards exist, this module only places and routes them.
 */

export interface GraphCard {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  column: number;
  row: number;
}

export interface GraphPlacement {
  cards: GraphCard[];
  headings: { label: string; x: number; y: number }[];
  columns: { left: number; right: number }[];
  rows: { top: number; bottom: number }[];
  width: number;
  height: number;
}

const LABELS: Record<string, string> = {
  web: 'Web',
  android: 'Android',
  http: 'HTTP API',
  voice: 'Voice',
  chat: 'Conversation',
  import: 'Imports',
  sensors: 'Sensors',
  ideas: 'Ideas',
  insights: 'Insights',
  engine: 'Analysis engines',
  admission: 'Admission',
  queue: 'Work queue',
  pipeline: 'Pipeline',
  llm: 'Language models',
  db: 'Database',
  system: 'Runtime',
};

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

const OVERVIEW_CAPTIONS = ['Clients', 'API', 'Workflows', 'Processing', 'Resources'];
const OVERVIEW_W = 176;
const OVERVIEW_H = 64;
const MODULE_W = 240;
const MODULE_H = 128;
const CHIP_W = 128;
const CHIP_H = 48;

export function componentLabel(id: string): string {
  return LABELS[id] ?? id;
}

export function layoutOverview(components: readonly string[]): GraphPlacement {
  const columns = Array.from({ length: 5 }, (_, column) => {
    const left = 24 + column * 224;
    return { left, right: left + OVERVIEW_W };
  });
  const rows = Array.from({ length: 6 }, (_, row) => {
    const top = 40 + row * 88;
    return { top, bottom: top + OVERVIEW_H };
  });
  const headings = OVERVIEW_CAPTIONS.map((label, column) => ({ label, x: columns[column].left, y: 24 }));
  const cards: GraphCard[] = [];
  const extras: string[] = [];
  for (const id of components) {
    const cell = OVERVIEW_CELLS[id];
    if (!cell) {
      extras.push(id);
      continue;
    }
    cards.push({
      id: `component:${id}`,
      x: columns[cell.column].left,
      y: rows[cell.row].top,
      width: OVERVIEW_W,
      height: OVERVIEW_H,
      column: cell.column,
      row: cell.row,
    });
  }
  extras.forEach((id, index) => {
    const column = index % 5;
    const extraRow = Math.floor(index / 5);
    const top = 608 + extraRow * 88;
    if (rows.length === 6 + extraRow) rows.push({ top, bottom: top + OVERVIEW_H });
    cards.push({
      id: `component:${id}`,
      x: columns[column].left,
      y: top,
      width: OVERVIEW_W,
      height: OVERVIEW_H,
      column,
      row: 6 + extraRow,
    });
  });
  if (extras.length > 0) headings.push({ label: 'Other components', x: columns[0].left, y: 596 });
  return {
    cards,
    headings,
    columns,
    rows,
    width: 1120,
    height: rows[rows.length - 1].bottom + 24,
  };
}

export function layoutComponent(input: {
  moduleIds: readonly string[];
  structure: readonly { source: string; target: string }[];
  incoming: readonly string[];
  outgoing: readonly string[];
  layoutWidth: number;
}): GraphPlacement {
  if (input.moduleIds.length === 0) {
    return { cards: [], headings: [], columns: [], rows: [], width: 0, height: 0 };
  }
  const order = new Map(input.moduleIds.map((id, index) => [id, index]));
  const present = new Set(input.moduleIds);
  const outgoing = new Map<string, string[]>();
  const layered = new Set<string>();
  for (const edge of input.structure) {
    if (!present.has(edge.source) || !present.has(edge.target) || edge.source === edge.target) continue;
    layered.add(edge.source);
    layered.add(edge.target);
    const targets = outgoing.get(edge.source) ?? [];
    if (!targets.includes(edge.target)) targets.push(edge.target);
    outgoing.set(edge.source, targets);
  }
  for (const targets of outgoing.values()) targets.sort((a, b) => a.localeCompare(b));

  const color = new Map<string, number>();
  const kept: { source: string; target: string }[] = [];
  const visit = (id: string) => {
    color.set(id, 1);
    for (const target of outgoing.get(id) ?? []) {
      const state = color.get(target) ?? 0;
      if (state === 1) continue;
      kept.push({ source: id, target });
      if (state === 0) visit(target);
    }
    color.set(id, 2);
  };
  for (const id of input.moduleIds) {
    if (layered.has(id) && (color.get(id) ?? 0) === 0) visit(id);
  }

  const predecessors = new Map<string, string[]>();
  for (const edge of kept) {
    const list = predecessors.get(edge.target) ?? [];
    list.push(edge.source);
    predecessors.set(edge.target, list);
  }
  const depthOf = new Map<string, number>();
  const depth = (id: string): number => {
    const cached = depthOf.get(id);
    if (cached != null) return cached;
    const parents = predecessors.get(id) ?? [];
    const value = parents.length === 0 ? 0 : 1 + Math.max(...parents.map(depth));
    depthOf.set(id, value);
    return value;
  };
  const layeredIds = input.moduleIds.filter(id => layered.has(id));
  const byDepth = new Map<number, string[]>();
  for (const id of layeredIds) {
    const column = depth(id);
    const list = byDepth.get(column) ?? [];
    list.push(id);
    byDepth.set(column, list);
  }
  const layeredColumns = byDepth.size === 0 ? 0 : Math.max(...byDepth.keys()) + 1;
  const rowOf = new Map<string, number>();
  for (let column = 0; column < layeredColumns; column += 1) {
    const ids = [...(byDepth.get(column) ?? [])];
    ids.sort((a, b) => {
      if (column === 0) return (order.get(a) ?? 0) - (order.get(b) ?? 0);
      const mean = (id: string) => {
        const parents = (predecessors.get(id) ?? []).filter(parent => depth(parent) < column);
        if (parents.length === 0) return Number.POSITIVE_INFINITY;
        return parents.reduce((sum, parent) => sum + (rowOf.get(parent) ?? 0), 0) / parents.length;
      };
      const delta = mean(a) - mean(b);
      return delta === 0 ? (order.get(a) ?? 0) - (order.get(b) ?? 0) : delta;
    });
    ids.forEach((id, row) => rowOf.set(id, row));
  }

  const standalone = input.moduleIds.filter(id => !layered.has(id));
  const fitted = Math.min(4, Math.max(1, Math.floor((input.layoutWidth - 352) / 288)));
  const moduleColumns = standalone.length > 0 ? Math.max(layeredColumns, fitted) : layeredColumns;
  const columns = [{ left: 24, right: 152 }];
  for (let column = 0; column < moduleColumns; column += 1) {
    const left = 200 + column * 288;
    columns.push({ left, right: left + MODULE_W });
  }
  const rightLeft = 200 + moduleColumns * 288;
  columns.push({ left: rightLeft, right: rightLeft + CHIP_W });

  const layeredRowCount = layeredIds.length === 0 ? 0 : Math.max(...rowOf.values()) + 1;
  const rows: { top: number; bottom: number }[] = [];
  for (let row = 0; row < layeredRowCount; row += 1) {
    const top = 40 + row * 160;
    rows.push({ top, bottom: top + MODULE_H });
  }
  const standaloneOrigin = layeredRowCount === 0 ? 40 : rows[layeredRowCount - 1].bottom + 40;
  const standaloneRows = standalone.length === 0 ? 0 : Math.ceil(standalone.length / moduleColumns);
  for (let row = 0; row < standaloneRows; row += 1) {
    const top = standaloneOrigin + row * 160;
    rows.push({ top, bottom: top + MODULE_H });
  }

  const cards: GraphCard[] = [];
  for (const id of layeredIds) {
    const column = depth(id);
    const row = rowOf.get(id) ?? 0;
    cards.push({
      id: `module:${id}`,
      x: columns[column + 1].left,
      y: rows[row].top,
      width: MODULE_W,
      height: MODULE_H,
      column: column + 1,
      row,
    });
  }
  standalone.forEach((id, index) => {
    const column = index % moduleColumns;
    const row = layeredRowCount + Math.floor(index / moduleColumns);
    cards.push({
      id: `module:${id}`,
      x: columns[column + 1].left,
      y: rows[row].top,
      width: MODULE_W,
      height: MODULE_H,
      column: column + 1,
      row,
    });
  });

  const nearestRow = (center: number) => {
    let best = 0;
    let bestDistance = Number.POSITIVE_INFINITY;
    rows.forEach((row, index) => {
      const distance = Math.abs((row.top + row.bottom) / 2 - center);
      if (distance < bestDistance) {
        best = index;
        bestDistance = distance;
      }
    });
    return best;
  };
  input.incoming.forEach((id, index) => {
    const y = 40 + index * 64;
    cards.push({
      id: `incoming:${id}`,
      x: 24,
      y,
      width: CHIP_W,
      height: CHIP_H,
      column: 0,
      row: nearestRow(y + CHIP_H / 2),
    });
  });
  input.outgoing.forEach((id, index) => {
    const y = 40 + index * 64;
    cards.push({
      id: `outgoing:${id}`,
      x: rightLeft,
      y,
      width: CHIP_W,
      height: CHIP_H,
      column: columns.length - 1,
      row: nearestRow(y + CHIP_H / 2),
    });
  });

  const headings = [
    { label: 'From other components', x: 24, y: 24 },
    { label: 'To other components', x: rightLeft, y: 24 },
  ];
  if (input.incoming.length === 0) headings.push({ label: 'None', x: 24, y: 40 });
  if (input.outgoing.length === 0) headings.push({ label: 'None', x: rightLeft, y: 40 });
  if (layeredIds.length > 0 && standalone.length > 0) {
    headings.push({ label: 'Other modules', x: 200, y: standaloneOrigin - 8 });
  }
  const lastRowBottom = rows.length > 0 ? rows[rows.length - 1].bottom : 0;
  const chipBottom = (count: number) => (count === 0 ? 0 : 40 + (count - 1) * 64 + CHIP_H);
  return {
    cards,
    headings,
    columns,
    rows,
    width: 352 + 288 * moduleColumns,
    height: Math.max(lastRowBottom, chipBottom(input.incoming.length), chipBottom(input.outgoing.length)) + 24,
  };
}

export function routeConnection(
  source: GraphCard,
  target: GraphCard,
  placement: GraphPlacement,
  slot: number,
): { x: number; y: number }[] {
  const offset = ((slot % 5) - 2) * 3;
  const start = { x: source.x + source.width, y: source.y + source.height / 2 };
  const end = { x: target.x, y: target.y + target.height / 2 };
  const xs = gutterAfter(placement, source.column) + offset;
  const xt = gutterBefore(placement, target.column) + offset;
  const forward = (x: number) => simplify([start, { x, y: start.y }, { x, y: end.y }, end]);
  if (target.column === source.column + 1) return forward(xs);
  if (target.column > source.column + 1) {
    const first = forward(xs);
    if (!crossesCard(first, source, target, placement)) return first;
    const second = forward(xt);
    if (!crossesCard(second, source, target, placement)) return second;
  }
  const below = Math.min(source.row, target.row);
  const cy = corridorBelow(placement, below) + offset;
  return simplify([
    start,
    { x: xs, y: start.y },
    { x: xs, y: cy },
    { x: xt, y: cy },
    { x: xt, y: end.y },
    end,
  ]);
}

export function pathData(points: readonly { x: number; y: number }[]): string {
  if (points.length === 0) return '';
  const parts = [`M ${round(points[0].x)} ${round(points[0].y)}`];
  if (points.length === 1) return parts[0];
  for (let index = 1; index < points.length - 1; index += 1) {
    const previous = points[index - 1];
    const current = points[index];
    const next = points[index + 1];
    const incoming = Math.hypot(current.x - previous.x, current.y - previous.y);
    const outgoing = Math.hypot(next.x - current.x, next.y - current.y);
    if (incoming === 0 || outgoing === 0) continue;
    const radius = Math.min(6, incoming / 2, outgoing / 2);
    const enter = {
      x: current.x - ((current.x - previous.x) / incoming) * radius,
      y: current.y - ((current.y - previous.y) / incoming) * radius,
    };
    const leave = {
      x: current.x + ((next.x - current.x) / outgoing) * radius,
      y: current.y + ((next.y - current.y) / outgoing) * radius,
    };
    parts.push(`L ${round(enter.x)} ${round(enter.y)}`);
    parts.push(`Q ${round(current.x)} ${round(current.y)} ${round(leave.x)} ${round(leave.y)}`);
  }
  const last = points[points.length - 1];
  parts.push(`L ${round(last.x)} ${round(last.y)}`);
  return parts.join(' ');
}

function gutterAfter(placement: GraphPlacement, column: number): number {
  const current = placement.columns[column];
  const next = placement.columns[column + 1];
  if (!current) return placement.width;
  if (!next) return (current.right + placement.width) / 2;
  return (current.right + next.left) / 2;
}

function gutterBefore(placement: GraphPlacement, column: number): number {
  const current = placement.columns[column];
  const previous = placement.columns[column - 1];
  if (!current) return 0;
  return ((previous ? previous.right : 0) + current.left) / 2;
}

function corridorBelow(placement: GraphPlacement, row: number): number {
  const current = placement.rows[row];
  if (!current) return placement.height / 2;
  const next = placement.rows[row + 1];
  if (!next) return (current.bottom + placement.height) / 2;
  return (current.bottom + next.top) / 2;
}

function simplify(points: { x: number; y: number }[]): { x: number; y: number }[] {
  const unique: { x: number; y: number }[] = [];
  for (const point of points) {
    const previous = unique[unique.length - 1];
    if (previous && previous.x === point.x && previous.y === point.y) continue;
    unique.push(point);
  }
  if (unique.length < 3) return unique;
  const simplified = [unique[0]];
  for (let index = 1; index < unique.length - 1; index += 1) {
    const previous = simplified[simplified.length - 1];
    const current = unique[index];
    const next = unique[index + 1];
    const vertical = previous.x === current.x && current.x === next.x;
    const horizontal = previous.y === current.y && current.y === next.y;
    if (!vertical && !horizontal) simplified.push(current);
  }
  simplified.push(unique[unique.length - 1]);
  return simplified;
}

function crossesCard(
  points: readonly { x: number; y: number }[],
  source: GraphCard,
  target: GraphCard,
  placement: GraphPlacement,
): boolean {
  return placement.cards.some(card => (
    card.id !== source.id && card.id !== target.id && points.some((point, index) => (
      index > 0 && segmentHits(points[index - 1], point, card, 4)
    ))
  ));
}

function segmentHits(
  start: { x: number; y: number },
  end: { x: number; y: number },
  card: GraphCard,
  pad: number,
): boolean {
  const left = card.x - pad;
  const right = card.x + card.width + pad;
  const top = card.y - pad;
  const bottom = card.y + card.height + pad;
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

function round(value: number): string {
  return String(Math.round(value * 1000) / 1000);
}

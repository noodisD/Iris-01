import type React from 'react';
import type { ReactElement, ReactNode } from 'react';
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Crosshair, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import type { ObsModuleEdge, ObsModuleNode, ObsSpanSummary } from '@/api/observatory';
import { ago, ms } from '@/lib/obsFormat';
import { IconButton } from '@/ui';
import {
  type GraphCard,
  type GraphPlacement,
  componentLabel,
  layoutComponent,
  layoutOverview,
  pathData,
  routeConnection,
} from './systemGraphLayout';
import styles from './ModuleGraph.module.css';

const BASELINE = [
  'web', 'android', 'http', 'voice', 'chat', 'import', 'sensors', 'ideas', 'insights',
  'engine', 'admission', 'queue', 'pipeline', 'llm', 'db', 'system',
];
const HTTP_ID = /^http:([A-Z]+) (.+)$/;
const MIN_K = 0.75;
const MAX_K = 2;
const KIND_TEXT: Record<ObsModuleEdge['kind'], string> = {
  call: 'Call',
  flow: 'Declared data flow',
  causal: 'Queued from',
};
const EVIDENCE_TEXT: Record<BundleEvidence, string> = {
  declared: 'declared, not observed in this window',
  observed: 'observed',
  mixed: 'mixed declared and observed relationships',
  pending: 'observed now, counts pending until the next snapshot',
};

export interface GraphPulse { moduleId: string; parentModuleId: string | null; error: boolean }

type Evidence = 'declared' | 'observed' | 'both' | 'pending';
type BundleEvidence = 'declared' | 'observed' | 'mixed' | 'pending';
type Camera = { x: number; y: number; k: number };

interface Member {
  source: string;
  target: string;
  kind: ObsModuleEdge['kind'];
  evidence: Evidence;
  calls: number | null;
  errors: number | null;
  p95_ms: number | null;
}

interface DrawnEdge {
  key: string;
  sourceId: string;
  targetId: string;
  sourceLabel: string;
  targetLabel: string;
  kind: ObsModuleEdge['kind'];
  evidence: BundleEvidence;
  calls: number | null;
  errors: number | null;
  p95_ms: number | null;
  members: Member[];
  points: { x: number; y: number }[];
}

type EdgeGroup = Omit<DrawnEdge, 'points' | 'evidence' | 'calls' | 'errors' | 'p95_ms'>;

function compareHttpIds(a: string, b: string): number {
  const ma = HTTP_ID.exec(a);
  const mb = HTTP_ID.exec(b);
  if (ma && mb) {
    if (ma[2] !== mb[2]) return ma[2] < mb[2] ? -1 : 1;
    if (ma[1] !== mb[1]) return ma[1] < mb[1] ? -1 : 1;
    return 0;
  }
  if (ma) return -1;
  if (mb) return 1;
  return a.localeCompare(b);
}

function pushMember(
  groups: Map<string, EdgeGroup>,
  key: string,
  sourceId: string,
  targetId: string,
  sourceLabel: string,
  targetLabel: string,
  member: Member,
) {
  const group = groups.get(key) ?? {
    key, sourceId, targetId, sourceLabel, targetLabel, kind: member.kind, members: [],
  };
  group.members.push(member);
  groups.set(key, group);
}

function aggregate(members: Member[]): { evidence: BundleEvidence; calls: number | null; errors: number | null; p95_ms: number | null } {
  const sum = (pick: (member: Member) => number | null): number | null => {
    let total: number | null = null;
    for (const member of members) {
      const value = pick(member);
      if (value == null) continue;
      total = (total ?? 0) + value;
    }
    return total;
  };
  const every = (test: (evidence: Evidence) => boolean) => members.every(member => test(member.evidence));
  const evidence: BundleEvidence = every(e => e === 'declared') ? 'declared'
    : every(e => e === 'observed' || e === 'both') ? 'observed'
    : every(e => e === 'pending') ? 'pending'
    : 'mixed';
  return {
    evidence,
    calls: sum(member => member.calls),
    errors: sum(member => member.errors),
    p95_ms: members.length === 1 ? members[0].p95_ms : null,
  };
}

function edgeTitle(edge: DrawnEdge): string {
  const pairs = edge.members.slice(0, 20).map(member => `${member.source} to ${member.target}`).join(', ');
  const more = edge.members.length > 20 ? `, and ${edge.members.length - 20} more` : '';
  return `${edge.sourceLabel} to ${edge.targetLabel}: ${KIND_TEXT[edge.kind]}; ${EVIDENCE_TEXT[edge.evidence]}; `
    + `${edge.calls ?? 'no measured'} calls; ${edge.errors ?? 'no measured'} errors; `
    + `p95 ${edge.p95_ms == null ? 'not aggregated' : ms(edge.p95_ms)}; `
    + `${edge.members.length} relationships: ${pairs}${more}`;
}

function chipTitle(members: Member[]): string {
  const pairs = members.slice(0, 20).map(member => `${member.source} to ${member.target}`).join(', ');
  const more = members.length > 20 ? `, and ${members.length - 20} more` : '';
  return `${members.length} relationships: ${pairs}${more}`;
}

function cardScreen(camera: Camera, card: GraphCard) {
  const left = card.x * camera.k + camera.x;
  const top = card.y * camera.k + camera.y;
  return { left, top, right: left + card.width * camera.k, bottom: top + card.height * camera.k };
}

function visibleWithMargin(camera: Camera, card: GraphCard, viewport: { width: number; height: number }, margin: number): boolean {
  const { left, top, right, bottom } = cardScreen(camera, card);
  return left >= margin && top >= margin && right <= viewport.width - margin && bottom <= viewport.height - margin;
}

function ensureVisible(camera: Camera, card: GraphCard, viewport: { width: number; height: number }): Camera {
  const margin = 24;
  const { left, top, right, bottom } = cardScreen(camera, card);
  let { x, y } = camera;
  if (card.width * camera.k <= viewport.width - margin * 2) {
    if (left < margin) x += margin - left;
    else if (right > viewport.width - margin) x -= right - (viewport.width - margin);
  }
  if (card.height * camera.k <= viewport.height - margin * 2) {
    if (top < margin) y += margin - top;
    else if (bottom > viewport.height - margin) y -= bottom - (viewport.height - margin);
  }
  return { ...camera, x, y };
}

export function ModuleGraph({
  nodes, edges, active, pendingEdges, component, selected, reach, connections,
  pulses, layoutWidth, status, onOpenComponent, onSelect,
}: {
  nodes: ObsModuleNode[];
  edges: ObsModuleEdge[];
  active: ObsSpanSummary[];
  pendingEdges: { source: string; target: string }[];
  component: string | null;
  selected: string | null;
  reach: 'all' | 'upstream' | 'downstream';
  connections: 'all' | 'observed';
  pulses: GraphPulse[];
  layoutWidth: number;
  status: ReactNode;
  onOpenComponent: (component: string) => void;
  onSelect: (moduleId: string) => void;
}): ReactElement {
  const hostRef = useRef<HTMLDivElement>(null);
  const minimapRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [camera, setCameraState] = useState<Camera>({ x: 0, y: 0, k: 1 });
  const [hovered, setHovered] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef<{ pointerId: number; x: number; y: number; vx: number; vy: number; k: number } | null>(null);
  const minimapDrag = useRef(false);
  /** Per scope: the world point at the viewport centre, so a restore survives viewport resizes. */
  const cameraCache = useRef<Record<string, { wx: number; wy: number; k: number }>>({});
  const awaitingInitial = useRef(true);
  const lastViewport = useRef({ width: 0, height: 0 });
  const unknownOrder = useRef<string[] | null>(null);
  const orderRef = useRef<Record<string, string[]>>({});
  const scopeKey = component == null ? 'overview' : `component:${component}`;
  const scopeKeyRef = useRef(scopeKey);
  const viewportRef = useRef(viewport);
  viewportRef.current = viewport;

  const nodesById = useMemo(() => new Map(nodes.map(node => [node.id, node])), [nodes]);

  const componentIds = useMemo(() => {
    const present = new Set(nodes.map(node => node.component));
    if (unknownOrder.current == null) {
      unknownOrder.current = [...present].filter(id => !BASELINE.includes(id)).sort((a, b) => a.localeCompare(b));
    } else {
      for (const id of [...present].sort((a, b) => a.localeCompare(b))) {
        if (!BASELINE.includes(id) && !unknownOrder.current.includes(id)) unknownOrder.current.push(id);
      }
    }
    return [...BASELINE.filter(id => present.has(id)), ...unknownOrder.current.filter(id => present.has(id))];
  }, [nodes]);

  const ordered = useMemo(() => {
    const byComponent = new Map<string, ObsModuleNode[]>();
    for (const node of nodes) {
      const list = byComponent.get(node.component) ?? [];
      list.push(node);
      byComponent.set(node.component, list);
    }
    const next: Record<string, string[]> = { ...orderRef.current };
    for (const [componentId, list] of byComponent) {
      const known = next[componentId] ?? [];
      const knownSet = new Set(known);
      const fresh = list.map(node => node.id).filter(id => !knownSet.has(id));
      fresh.sort((a, b) => a.localeCompare(b));
      if (known.length === 0) {
        if (componentId === 'http') fresh.sort(compareHttpIds);
        next[componentId] = fresh;
      } else {
        const presentSet = new Set(list.map(node => node.id));
        next[componentId] = [...known.filter(id => presentSet.has(id)), ...fresh];
      }
    }
    orderRef.current = next;
    return next;
  }, [nodes]);

  const scopeIds = useMemo(
    () => new Set(component == null ? [] : ordered[component] ?? []),
    [ordered, component],
  );

  const filtered = useMemo(() => {
    const real = (connections === 'observed' ? edges.filter(edge => edge.evidence !== 'declared') : edges)
      .map(edge => ({
        source: edge.source, target: edge.target, kind: edge.kind,
        evidence: edge.evidence as Evidence, calls: edge.calls, errors: edge.errors, p95_ms: edge.p95_ms,
      }));
    const pending = pendingEdges.map(edge => ({
      source: edge.source, target: edge.target, kind: 'call' as const,
      evidence: 'pending' as Evidence, calls: null, errors: null, p95_ms: null,
    }));
    return [...real, ...pending];
  }, [edges, pendingEdges, connections]);

  const chipData = useMemo(() => {
    const incoming = new Map<string, Member[]>();
    const outgoing = new Map<string, Member[]>();
    if (component != null) {
      for (const edge of filtered) {
        const sourceIn = scopeIds.has(edge.source);
        const targetIn = scopeIds.has(edge.target);
        if (sourceIn === targetIn) continue;
        const sourceNode = nodesById.get(edge.source);
        const targetNode = nodesById.get(edge.target);
        if (!sourceNode || !targetNode) continue;
        if (targetIn) {
          const list = incoming.get(sourceNode.component) ?? [];
          list.push(edge);
          incoming.set(sourceNode.component, list);
        } else {
          const list = outgoing.get(targetNode.component) ?? [];
          list.push(edge);
          outgoing.set(targetNode.component, list);
        }
      }
    }
    return {
      incoming: [...incoming.keys()].sort((a, b) => a.localeCompare(b)),
      outgoing: [...outgoing.keys()].sort((a, b) => a.localeCompare(b)),
      incomingMembers: incoming,
      outgoingMembers: outgoing,
    };
  }, [filtered, scopeIds, nodesById, component]);

  const structure = useMemo(() => {
    if (component == null) return [];
    return edges
      .filter(edge => (edge.kind === 'call' || edge.kind === 'flow') && (edge.evidence === 'declared' || edge.evidence === 'both'))
      .filter(edge => scopeIds.has(edge.source) && scopeIds.has(edge.target))
      .map(edge => ({ source: edge.source, target: edge.target }));
  }, [edges, scopeIds, component]);

  const placement: GraphPlacement = useMemo(() => {
    if (component == null) return layoutOverview(componentIds);
    return layoutComponent({
      moduleIds: ordered[component] ?? [],
      structure,
      incoming: chipData.incoming,
      outgoing: chipData.outgoing,
      layoutWidth,
    });
  }, [component, componentIds, ordered, structure, chipData, layoutWidth]);
  const placementRef = useRef(placement);
  placementRef.current = placement;

  const drawn = useMemo(() => {
    const groups = new Map<string, EdgeGroup>();
    const moduleLabel = (id: string) => nodesById.get(id)?.label ?? id;
    if (component == null) {
      for (const edge of filtered) {
        const sourceNode = nodesById.get(edge.source);
        const targetNode = nodesById.get(edge.target);
        if (!sourceNode || !targetNode) continue;
        if (sourceNode.component === targetNode.component) continue;
        const sourceId = `component:${sourceNode.component}`;
        const targetId = `component:${targetNode.component}`;
        pushMember(
          groups,
          `${sourceId}|${targetId}|${edge.kind}`,
          sourceId, targetId,
          componentLabel(sourceNode.component), componentLabel(targetNode.component),
          edge,
        );
      }
    } else {
      for (const edge of filtered) {
        const sourceIn = scopeIds.has(edge.source);
        const targetIn = scopeIds.has(edge.target);
        if (sourceIn && targetIn) {
          pushMember(
            groups,
            `${edge.source}|${edge.target}|${edge.kind}`,
            `module:${edge.source}`, `module:${edge.target}`,
            moduleLabel(edge.source), moduleLabel(edge.target),
            edge,
          );
        } else if (sourceIn !== targetIn) {
          const otherComponent = targetIn ? nodesById.get(edge.source)?.component : nodesById.get(edge.target)?.component;
          if (!otherComponent) continue;
          const moduleId = targetIn ? edge.target : edge.source;
          const chipId = targetIn ? `incoming:${otherComponent}` : `outgoing:${otherComponent}`;
          const chipLabel = componentLabel(otherComponent);
          pushMember(
            groups,
            `${chipId}|${moduleId}|${edge.kind}`,
            targetIn ? chipId : `module:${edge.source}`,
            targetIn ? `module:${edge.target}` : chipId,
            targetIn ? chipLabel : moduleLabel(edge.source),
            targetIn ? moduleLabel(edge.target) : chipLabel,
            edge,
          );
        }
      }
    }
    const byCard = new Map(placement.cards.map(card => [card.id, card]));
    const list = [...groups.values()].sort((a, b) => a.key.localeCompare(b.key));
    const result: DrawnEdge[] = [];
    list.forEach((group, slot) => {
      const sourceCard = byCard.get(group.sourceId);
      const targetCard = byCard.get(group.targetId);
      if (!sourceCard || !targetCard) return;
      const bundle = aggregate(group.members);
      result.push({
        ...group,
        ...bundle,
        members: group.members,
        points: routeConnection(sourceCard, targetCard, placement, slot),
      });
    });
    return result;
  }, [filtered, component, scopeIds, nodesById, placement]);

  const running = useMemo(() => {
    const counts = new Map<string, number>();
    for (const span of active) {
      if (!span.module_id) continue;
      if (component == null) {
        const spanComponent = nodesById.get(span.module_id)?.component ?? span.component;
        if (!spanComponent) continue;
        const id = `component:${spanComponent}`;
        counts.set(id, (counts.get(id) ?? 0) + 1);
      } else if (scopeIds.has(span.module_id)) {
        const id = `module:${span.module_id}`;
        counts.set(id, (counts.get(id) ?? 0) + 1);
      }
    }
    return counts;
  }, [active, component, nodesById, scopeIds]);

  const reachIds = useMemo(() => {
    if (reach === 'all' || !selected || component == null) return null;
    const forward = new Map<string, string[]>();
    const backward = new Map<string, string[]>();
    for (const edge of edges) {
      const sources = forward.get(edge.source) ?? [];
      sources.push(edge.target);
      forward.set(edge.source, sources);
      const targets = backward.get(edge.target) ?? [];
      targets.push(edge.source);
      backward.set(edge.target, targets);
    }
    const seen = new Set<string>([selected]);
    const stack = [selected];
    const nextOf = reach === 'downstream' ? forward : backward;
    while (stack.length > 0) {
      const current = stack.pop() ?? '';
      for (const next of nextOf.get(current) ?? []) {
        if (seen.has(next)) continue;
        seen.add(next);
        stack.push(next);
      }
    }
    return seen;
  }, [reach, selected, edges, component]);

  const pulseCards = useMemo(() => {
    const ids = new Map<string, boolean>();
    for (const pulse of pulses) {
      const spanComponent = pulse.moduleId ? nodesById.get(pulse.moduleId)?.component : undefined;
      if (component == null) {
        if (spanComponent) ids.set(`component:${spanComponent}`, pulse.error);
      } else if (pulse.moduleId && scopeIds.has(pulse.moduleId)) {
        ids.set(`module:${pulse.moduleId}`, pulse.error);
      } else if (pulse.parentModuleId && pulse.moduleId && spanComponent && scopeIds.has(pulse.parentModuleId)) {
        ids.set(`outgoing:${spanComponent}`, pulse.error);
      }
    }
    return ids;
  }, [pulses, component, nodesById, scopeIds]);

  const pulseEdgeKeys = useMemo(() => {
    const keys = new Map<string, boolean>();
    for (const pulse of pulses) {
      if (!pulse.parentModuleId) continue;
      for (const edge of drawn) {
        if (edge.members.some(member => member.source === pulse.parentModuleId && member.target === pulse.moduleId)) {
          keys.set(edge.key, pulse.error);
        }
      }
    }
    return keys;
  }, [pulses, drawn]);

  const overviewData = useMemo(() => {
    if (component != null) return null;
    const data = new Map<string, { count: number; calls: number; errors: number }>();
    for (const node of nodes) {
      const entry = data.get(node.component) ?? { count: 0, calls: 0, errors: 0 };
      entry.count += 1;
      entry.calls += node.stats?.calls ?? 0;
      entry.errors += node.stats?.errors ?? 0;
      data.set(node.component, entry);
    }
    return data;
  }, [nodes, component]);

  const internalCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const edge of edges) {
      const sourceNode = nodesById.get(edge.source);
      const targetNode = nodesById.get(edge.target);
      if (!sourceNode || !targetNode || sourceNode.component !== targetNode.component) continue;
      counts.set(sourceNode.component, (counts.get(sourceNode.component) ?? 0) + 1);
    }
    return counts;
  }, [edges, nodesById]);

  const applyCamera = (updater: (current: Camera) => Camera) => {
    setCameraState(current => {
      const next = updater(current);
      const clamped = { ...next, k: Math.min(MAX_K, Math.max(MIN_K, next.k)) };
      const vp = viewportRef.current;
      cameraCache.current[scopeKeyRef.current] = {
        wx: (vp.width / 2 - clamped.x) / clamped.k,
        wy: (vp.height / 2 - clamped.y) / clamped.k,
        k: clamped.k,
      };
      return clamped;
    });
  };

  const initialView = (): Camera => {
    const vp = viewportRef.current;
    if (vp.width === 0 || vp.height === 0) return { x: 0, y: 0, k: 1 };
    if (component == null) {
      const world = placementRef.current;
      if (world.width <= vp.width && world.height <= vp.height) {
        return { x: (vp.width - world.width) / 2, y: (vp.height - world.height) / 2, k: 1 };
      }
      return { x: 0, y: 0, k: 1 };
    }
    const card = selected ? placementRef.current.cards.find(item => item.id === `module:${selected}`) : null;
    if (card) {
      return { x: vp.width / 2 - (card.x + card.width / 2), y: vp.height / 2 - (card.y + card.height / 2), k: 1 };
    }
    return { x: 0, y: 0, k: 1 };
  };

  useEffect(() => {
    scopeKeyRef.current = scopeKey;
    const cached = cameraCache.current[scopeKey];
    if (cached) {
      awaitingInitial.current = false;
      const vp = viewportRef.current;
      setCameraState({ k: cached.k, x: vp.width / 2 - cached.wx * cached.k, y: vp.height / 2 - cached.wy * cached.k });
      return;
    }
    awaitingInitial.current = viewportRef.current.width === 0;
    setCameraState(initialView());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeKey]);

  useEffect(() => {
    const element = hostRef.current;
    if (!element) return;
    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        const width = entry.contentRect.width;
        const height = entry.contentRect.height;
        if (width === 0 || height === 0) continue;
        setViewport(prev => (prev.width === width && prev.height === height ? prev : { width, height }));
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const previous = lastViewport.current;
    if (previous.width === viewport.width && previous.height === viewport.height) return;
    lastViewport.current = viewport;
    if (previous.width === 0 || previous.height === 0) {
      if (awaitingInitial.current) {
        awaitingInitial.current = false;
        setCameraState(initialView());
      }
      return;
    }
    if (viewport.width === 0 || viewport.height === 0) return;
    applyCamera(current => {
      const card = selected && component != null
        ? placementRef.current.cards.find(item => item.id === `module:${selected}`) ?? null
        : null;
      if (card) return ensureVisible(current, card, viewport);
      return {
        ...current,
        x: current.x + (viewport.width - previous.width) / 2,
        y: current.y + (viewport.height - previous.height) / 2,
      };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewport, selected, component]);

  useLayoutEffect(() => {
    if (!selected) return;
    const vp = viewportRef.current;
    if (vp.width === 0 || vp.height === 0) return;
    const card = placementRef.current.cards.find(item => item.id === `module:${selected}`);
    if (!card) return;
    applyCamera(current => {
      if (visibleWithMargin(current, card, vp, 24)) return current;
      return { k: 1, x: vp.width / 2 - (card.x + card.width / 2), y: vp.height / 2 - (card.y + card.height / 2) };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, scopeKey]);

  const zoomAround = (clientX: number, clientY: number, factor: number) => {
    const host = hostRef.current;
    const vp = viewportRef.current;
    if (!host || vp.width === 0) return;
    const rect = host.getBoundingClientRect();
    const px = clientX - rect.left;
    const py = clientY - rect.top;
    applyCamera(current => {
      const k = Math.min(MAX_K, Math.max(MIN_K, current.k * factor));
      const worldX = (px - current.x) / current.k;
      const worldY = (py - current.y) / current.k;
      return { k, x: px - worldX * k, y: py - worldY * k };
    });
  };

  const zoomByCentre = (factor: number) => {
    const vp = viewportRef.current;
    zoomAround(vp.width / 2, vp.height / 2, factor);
  };

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      if (event.ctrlKey || event.metaKey) {
        zoomAround(event.clientX, event.clientY, event.deltaY < 0 ? 1.1 : 1 / 1.1);
      } else {
        applyCamera(current => ({ ...current, x: current.x - event.deltaX, y: current.y - event.deltaY }));
      }
    };
    host.addEventListener('wheel', onWheel, { passive: false });
    return () => host.removeEventListener('wheel', onWheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onHostKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return;
    const pan = 64;
    if (event.key === 'ArrowLeft') { event.preventDefault(); applyCamera(c => ({ ...c, x: c.x + pan })); }
    else if (event.key === 'ArrowRight') { event.preventDefault(); applyCamera(c => ({ ...c, x: c.x - pan })); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); applyCamera(c => ({ ...c, y: c.y + pan })); }
    else if (event.key === 'ArrowDown') { event.preventDefault(); applyCamera(c => ({ ...c, y: c.y - pan })); }
    else if (event.key === '+' || event.key === '=') { event.preventDefault(); zoomByCentre(1.25); }
    else if (event.key === '-' || event.key === '_') { event.preventDefault(); zoomByCentre(1 / 1.25); }
  };

  const onHostFocusIn = (event: React.FocusEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    if (!target.dataset.displayId) return;
    const host = hostRef.current;
    if (!host) return;
    const hostRect = host.getBoundingClientRect();
    const rect = target.getBoundingClientRect();
    const margin = 24;
    const left = rect.left - hostRect.left;
    const top = rect.top - hostRect.top;
    const right = left + rect.width;
    const bottom = top + rect.height;
    let dx = 0;
    let dy = 0;
    if (left < margin) dx = margin - left;
    else if (right > hostRect.width - margin) dx = hostRect.width - margin - right;
    if (top < margin) dy = margin - top;
    else if (bottom > hostRect.height - margin) dy = hostRect.height - margin - bottom;
    if (dx !== 0 || dy !== 0) applyCamera(c => ({ ...c, x: c.x + dx, y: c.y + dy }));
  };

  const onHostPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    const target = event.target as Element;
    if (target.closest('button')) return;
    if (minimapRef.current?.contains(target)) return;
    dragRef.current = {
      pointerId: event.pointerId, x: event.clientX, y: event.clientY,
      vx: camera.x, vy: camera.y, k: camera.k,
    };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    setDragging(true);
  };

  const onHostPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    applyCamera(() => ({
      k: drag.k,
      x: drag.vx + event.clientX - drag.x,
      y: drag.vy + event.clientY - drag.y,
    }));
  };

  const endDrag = () => {
    dragRef.current = null;
    setDragging(false);
  };

  const centreFromMinimap = (event: React.PointerEvent<HTMLDivElement>) => {
    const element = minimapRef.current;
    const vp = viewportRef.current;
    if (!element || vp.width === 0 || placement.width === 0) return;
    const rect = element.getBoundingClientRect();
    const localX = ((event.clientX - rect.left) / rect.width) * 176;
    const localY = ((event.clientY - rect.top) / rect.height) * 112;
    const worldX = (localX - miniOffsetX) / miniScale;
    const worldY = (localY - miniOffsetY) / miniScale;
    applyCamera(current => ({ ...current, x: vp.width / 2 - worldX * current.k, y: vp.height / 2 - worldY * current.k }));
  };

  const onMinimapPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    minimapDrag.current = true;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    centreFromMinimap(event);
  };

  const onMinimapPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (minimapDrag.current) centreFromMinimap(event);
  };

  const endMinimapDrag = () => {
    minimapDrag.current = false;
  };

  const resetView = () => {
    delete cameraCache.current[scopeKeyRef.current];
    awaitingInitial.current = viewportRef.current.width === 0;
    setCameraState(initialView());
  };

  const centreSelection = () => {
    if (!selectedCardId) return;
    const card = placementRef.current.cards.find(item => item.id === selectedCardId);
    const vp = viewportRef.current;
    if (!card || vp.width === 0) return;
    applyCamera(() => ({ k: 1, x: vp.width / 2 - (card.x + card.width / 2), y: vp.height / 2 - (card.y + card.height / 2) }));
  };

  const ready = layoutWidth > 0 && viewport.width > 0 && viewport.height > 0;
  const cards = useMemo(() => [...placement.cards].sort((a, b) => a.column - b.column || a.row - b.row), [placement]);
  const selectedCardId = selected != null && component != null ? `module:${selected}` : null;
  const focusCardId = hovered ?? selectedCardId;

  const miniScale = placement.width > 0 && placement.height > 0
    ? Math.min(176 / placement.width, 112 / placement.height)
    : 1;
  const miniOffsetX = (176 - placement.width * miniScale) / 2;
  const miniOffsetY = (112 - placement.height * miniScale) / 2;
  const showMinimap = ready && placement.width > 0 && placement.height > 0
    && (placement.width * camera.k > viewport.width || placement.height * camera.k > viewport.height);

  const moduleCards = useMemo(() => placement.cards.filter(card => card.id.startsWith('module:')), [placement]);
  const boundary = useMemo(() => {
    if (component == null || moduleCards.length === 0) return null;
    const left = Math.min(...moduleCards.map(card => card.x));
    const top = Math.min(...moduleCards.map(card => card.y));
    const right = Math.max(...moduleCards.map(card => card.x + card.width));
    const bottom = Math.max(...moduleCards.map(card => card.y + card.height));
    return { x: left - 16, y: top - 16, width: right - left + 32, height: bottom - top + 32 };
  }, [component, moduleCards]);

  const memberConnectsReached = (member: Member): boolean => {
    if (reachIds == null) return true;
    const sourceReached = !scopeIds.has(member.source) || reachIds.has(member.source);
    const targetReached = !scopeIds.has(member.target) || reachIds.has(member.target);
    return sourceReached && targetReached;
  };

  const edgeIsReached = (edge: DrawnEdge): boolean => edge.members.every(memberConnectsReached);

  const chipIsReached = (cardId: string): boolean => {
    if (reachIds == null) return true;
    const direction = cardId.startsWith('incoming:') ? chipData.incomingMembers : chipData.outgoingMembers;
    const members = direction.get(cardId.slice(cardId.indexOf(':') + 1)) ?? [];
    return members.some(memberConnectsReached);
  };

  const cardIsDimmed = (cardId: string): boolean => {
    if (reachIds == null) return false;
    if (cardId === selectedCardId) return false;
    if (cardId.startsWith('module:')) return !reachIds.has(cardId.slice('module:'.length));
    if (cardId.startsWith('incoming:') || cardId.startsWith('outgoing:')) return !chipIsReached(cardId);
    return false;
  };

  const edgeClasses = (edge: DrawnEdge): string => {
    const incident = focusCardId != null && (edge.sourceId === focusCardId || edge.targetId === focusCardId);
    const hot = incident && focusCardId != null;
    const dashed = edge.kind !== 'call' || edge.evidence === 'declared' || edge.evidence === 'pending';
    const classes = [
      styles.edge,
      (edge.errors ?? 0) > 0 ? styles.edgeError : null,
      dashed ? styles.edgeDashed : null,
      hot ? styles.edgeHot : null,
      !hot && focusCardId != null ? (hovered != null ? styles.edgeQuiet : styles.edgeDim) : null,
      reachIds != null && !hot && !edgeIsReached(edge) ? styles.edgeFaint : null,
      pulseEdgeKeys.has(edge.key) ? (pulseEdgeKeys.get(edge.key) ? styles.pulseBad : styles.pulse) : null,
    ];
    return classes.filter(Boolean).join(' ');
  };

  const renderOverviewCard = (card: GraphCard) => {
    const id = card.id.slice('component:'.length);
    const data = overviewData?.get(id) ?? { count: 0, calls: 0, errors: 0 };
    const runs = running.get(card.id) ?? 0;
    const internal = internalCounts.get(id) ?? 0;
    const ariaLabel = `${componentLabel(id)}, ${id}, ${data.count} modules, ${internal} internal relationships, `
      + `${data.calls} invocations, ${data.errors} errors, ${runs} running. Open component.`;
    return (
      <button
        key={card.id}
        type="button"
        data-display-id={card.id}
        className={`${styles.componentCard} ${cardIsDimmed(card.id) ? styles.faint : ''} ${pulseCards.has(card.id) ? styles.cardPulse : ''}`.trim()}
        style={{ left: card.x, top: card.y, width: card.width, height: card.height }}
        aria-label={ariaLabel}
        onClick={() => onOpenComponent(id)}
        onMouseEnter={() => setHovered(card.id)}
        onMouseLeave={() => setHovered(null)}
        onFocus={() => setHovered(card.id)}
        onBlur={() => setHovered(null)}
      >
        <span className={styles.cardTitle}>{componentLabel(id)}</span>
        <span className={styles.cardMeta}>
          {data.count} {data.count === 1 ? 'module' : 'modules'},{' '}
          {runs > 0 ? <span className={styles.textIris}>{runs} running</span>
            : data.errors > 0 ? <span className={styles.textWorse}>{data.errors} errors</span>
            : data.calls > 0 ? `${data.calls} invocations`
            : 'not observed'}
        </span>
      </button>
    );
  };

  const renderModuleCard = (card: GraphCard) => {
    const id = card.id.slice('module:'.length);
    const node = nodesById.get(id);
    if (!node) return null;
    const httpMatch = HTTP_ID.exec(node.id);
    const line1 = httpMatch ? `/${httpMatch[2].replace(/^\//, '')}` : node.label;
    const runs = running.get(card.id) ?? 0;
    const inputs = node.inputs.join(', ') || '—';
    const outputs = node.outputs.join(', ') || '—';
    let stateText: string;
    if (runs > 0) stateText = `${runs} running`;
    else if (node.kind === 'state') stateText = node.latest_state ? `Snapshot received ${ago(node.latest_state.received_at)}` : 'No snapshot';
    else if (node.stats) stateText = `${node.stats.calls} calls, ${node.stats.errors} errors, p95 ${ms(node.stats.p95_ms)}`;
    else stateText = 'Not observed in this window';
    const fullText = `${line1}, ${node.id}, In ${inputs}, Out ${outputs}, ${stateText}`;
    const cardAria = `${fullText}. Select module.`;
    return (
      <button
        key={card.id}
        type="button"
        data-display-id={card.id}
        data-selected={card.id === selectedCardId ? 'true' : undefined}
        aria-current={card.id === selectedCardId ? 'true' : undefined}
        className={`${styles.moduleCard} ${cardIsDimmed(card.id) ? styles.faint : ''} ${pulseCards.has(card.id) ? styles.cardPulse : ''}`.trim()}
        style={{ left: card.x, top: card.y, width: card.width, height: card.height }}
        title={cardAria}
        aria-label={cardAria}
        onClick={() => onSelect(id)}
        onMouseEnter={() => setHovered(card.id)}
        onMouseLeave={() => setHovered(null)}
        onFocus={() => setHovered(card.id)}
        onBlur={() => setHovered(null)}
      >
        <span className={styles.cardTitle}>{line1}</span>
        <span className={styles.cardId}>{node.id}</span>
        <span className={styles.cardLine}><span className={styles.lineLabel}>In</span> {inputs}</span>
        <span className={styles.cardLine}><span className={styles.lineLabel}>Out</span> {outputs}</span>
        <span className={styles.cardLine}>
          {runs > 0 ? <span className={styles.textIris}>{runs} running</span>
            : node.kind === 'state' ? stateText
            : node.stats ? (
              <>
                {node.stats.calls} calls,{' '}
                {node.stats.errors > 0 ? <span className={styles.textWorse}>{node.stats.errors} errors</span> : `${node.stats.errors} errors`},{' '}
                p95 {ms(node.stats.p95_ms)}
              </>
            )
            : 'Not observed in this window'}
        </span>
      </button>
    );
  };

  const renderChipCard = (card: GraphCard) => {
    const direction = card.id.startsWith('incoming:') ? 'incoming' : 'outgoing';
    const id = card.id.slice(card.id.indexOf(':') + 1);
    const members = (direction === 'incoming' ? chipData.incomingMembers : chipData.outgoingMembers).get(id) ?? [];
    const ariaLabel = `${componentLabel(id)}, ${id}, ${members.length} relationships to this component. Open component.`;
    return (
      <button
        key={card.id}
        type="button"
        data-display-id={card.id}
        className={`${styles.chipCard} ${cardIsDimmed(card.id) ? styles.faint : ''} ${pulseCards.has(card.id) ? styles.cardPulse : ''}`.trim()}
        style={{ left: card.x, top: card.y, width: card.width, height: card.height }}
        title={chipTitle(members)}
        aria-label={ariaLabel}
        onClick={() => onOpenComponent(id)}
        onMouseEnter={() => setHovered(card.id)}
        onMouseLeave={() => setHovered(null)}
        onFocus={() => setHovered(card.id)}
        onBlur={() => setHovered(null)}
      >
        <span className={styles.chipTitle}>{componentLabel(id)}</span>
        <span className={styles.chipMeta}>{members.length} {members.length === 1 ? 'relationship' : 'relationships'}</span>
      </button>
    );
  };

  const helpId = useId();
  const markerId = `arrow-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;
  const longestSegment = (points: { x: number; y: number }[]) => {
    let best = { a: points[0], b: points[1] };
    let bestLength = -1;
    for (let index = 1; index < points.length; index += 1) {
      const a = points[index - 1];
      const b = points[index];
      const length = Math.abs(b.x - a.x) + Math.abs(b.y - a.y);
      if (length > bestLength) {
        bestLength = length;
        best = { a, b };
      }
    }
    return best;
  };

  return (
    <section className={styles.frame} aria-label="System map">
      <div className={styles.frameHeader}>
        <div className={styles.status}>{status}</div>
        <div className={styles.headerTools}>
          <div className={styles.legendSlot}><GraphLegend /></div>
          <IconButton label="Zoom in" icon={<ZoomIn />} onClick={() => zoomByCentre(1.25)} />
          <IconButton label="Zoom out" icon={<ZoomOut />} onClick={() => zoomByCentre(1 / 1.25)} />
          <IconButton label="Center selection" icon={<Crosshair />} disabled={!selectedCardId} onClick={centreSelection} />
          <IconButton label="Reset view" icon={<RotateCcw />} onClick={resetView} />
        </div>
      </div>
      <div
        ref={hostRef}
        className={`${styles.viewportHost} ${dragging ? styles.grabbing : ''}`.trim()}
        tabIndex={0}
        role="group"
        aria-label="Map viewport"
        aria-describedby={helpId}
        style={{
          backgroundColor: 'var(--night)',
          backgroundImage: 'radial-gradient(var(--mist) 1px, transparent 1px)',
          backgroundSize: `${22 * camera.k}px ${22 * camera.k}px`,
          backgroundPosition: `${camera.x}px ${camera.y}px`,
        }}
        onKeyDown={onHostKeyDown}
        onFocus={onHostFocusIn}
        onScroll={event => {
          const host = event.currentTarget;
          const dx = host.scrollLeft;
          const dy = host.scrollTop;
          if (dx === 0 && dy === 0) return;
          host.scrollLeft = 0;
          host.scrollTop = 0;
          applyCamera(c => ({ ...c, x: c.x - dx, y: c.y - dy }));
        }}
        onPointerDown={onHostPointerDown}
        onPointerMove={onHostPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onLostPointerCapture={endDrag}
      >
        <span id={helpId} className="visually-hidden">Arrow keys pan. Plus and minus zoom.</span>
        {ready && (
          <>
            <svg className={styles.svgLayer} aria-hidden="true">
              <defs>
                <marker id={markerId} viewBox="0 0 8 8" markerWidth="7" markerHeight="7" refX="7" refY="4" orient="auto">
                  <path d="M1 1 L7 4 L1 7" className={styles.arrow} />
                </marker>
              </defs>
              <g transform={`translate(${camera.x} ${camera.y}) scale(${camera.k})`}>
                {component == null && placement.columns.slice(0, 5).map((column, index) => (
                  <rect
                    key={`region-${index}`}
                    className={styles.region}
                    x={column.left - 12}
                    y={8}
                    width={200}
                    height={placement.rows[5].bottom + 12 - 8}
                    rx={14}
                  />
                ))}
                {boundary && (
                  <rect
                    className={styles.boundary}
                    x={boundary.x}
                    y={boundary.y}
                    width={boundary.width}
                    height={boundary.height}
                    rx={14}
                  />
                )}
                {drawn.map(edge => {
                  const d = pathData(edge.points);
                  const label = (() => {
                    if (edge.kind !== 'causal' || edge.points.length < 2) return null;
                    const { a, b } = longestSegment(edge.points);
                    return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
                  })();
                  return (
                    <g key={edge.key}>
                      <path
                        d={d}
                        className={edgeClasses(edge)}
                        vectorEffect="non-scaling-stroke"
                        markerEnd={`url(#${markerId})`}
                      />
                      {label && (
                        <>
                          <rect className={styles.causalRect} x={label.x - 42} y={label.y - 9} width={84} height={18} rx={4} />
                          <text className={styles.causalText} x={label.x} y={label.y + 4} textAnchor="middle">Queued from</text>
                        </>
                      )}
                      <path d={d} className={styles.hitPath}>
                        <title>{edgeTitle(edge)}</title>
                      </path>
                    </g>
                  );
                })}
              </g>
            </svg>
            <div
              className={styles.cardLayer}
              style={{ transform: `translate(${camera.x}px, ${camera.y}px) scale(${camera.k})`, transformOrigin: '0 0' }}
            >
              {placement.headings.map(heading => (
                <span
                  key={`${heading.label}-${heading.x}-${heading.y}`}
                  className={heading.label === 'None' ? styles.headingNone : styles.heading}
                  style={{ left: heading.x, top: heading.y }}
                >
                  {heading.label}
                </span>
              ))}
              {cards.map(card => (
                card.id.startsWith('component:') ? renderOverviewCard(card)
                  : card.id.startsWith('module:') ? renderModuleCard(card)
                  : renderChipCard(card)
              ))}
            </div>
            {showMinimap && (
              <div
                ref={minimapRef}
                className={styles.minimap}
                aria-hidden="true"
                onPointerDown={onMinimapPointerDown}
                onPointerMove={onMinimapPointerMove}
                onPointerUp={endMinimapDrag}
                onPointerCancel={endMinimapDrag}
                onLostPointerCapture={endMinimapDrag}
              >
                <svg width="176" height="112" viewBox="0 0 176 112">
                  {placement.cards.map(card => (
                    <rect
                      key={card.id}
                      className={card.id === selectedCardId ? styles.miniSelected : styles.miniCard}
                      x={miniOffsetX + card.x * miniScale}
                      y={miniOffsetY + card.y * miniScale}
                      width={Math.max(2, card.width * miniScale)}
                      height={Math.max(2, card.height * miniScale)}
                      rx={2}
                    />
                  ))}
                  <rect
                    className={styles.miniViewport}
                    x={miniOffsetX + (-camera.x / camera.k) * miniScale}
                    y={miniOffsetY + (-camera.y / camera.k) * miniScale}
                    width={Math.min(176, (viewport.width / camera.k) * miniScale)}
                    height={Math.min(112, (viewport.height / camera.k) * miniScale)}
                  />
                </svg>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

export function GraphLegend(): ReactElement {
  return (
    <ul className={styles.legend}>
      <li className={styles.legendItem}>
        <svg width="20" height="8" viewBox="0 0 20 8" aria-hidden="true"><line x1="1" y1="4" x2="19" y2="4" className={styles.legendSolid} /></svg>
        Observed call
      </li>
      <li className={styles.legendItem}>
        <svg width="20" height="8" viewBox="0 0 20 8" aria-hidden="true"><line x1="1" y1="4" x2="19" y2="4" className={styles.legendDashed} /></svg>
        Declared, not observed
      </li>
      <li className={styles.legendItem}>
        <svg width="26" height="8" viewBox="0 0 26 8" aria-hidden="true">
          <line x1="1" y1="4" x2="25" y2="4" className={styles.legendDashed} />
          <rect x="9" y="1" width="8" height="6" rx="1" className={styles.legendLabel} />
        </svg>
        Queued from
      </li>
      <li className={styles.legendItem}>
        <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="3" className={styles.legendDot} /></svg>
        Running
      </li>
      <li className={styles.legendItem}>
        <svg width="20" height="8" viewBox="0 0 20 8" aria-hidden="true"><line x1="1" y1="4" x2="19" y2="4" className={styles.legendWorse} /></svg>
        Errors
      </li>
    </ul>
  );
}

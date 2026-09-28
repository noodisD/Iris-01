import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getAnalysis, getClients, getDatabase, getErrors, getInvocation, getLlm, getLogs, getModuleCalls,
  getOperations, getOverview, getQueue, getSamples, getSystem, getTrace, getTraces, liveUrl,
  type LiveFilters, type ObsHealth, type ObsLog, type ObsSpanSummary,
} from '@/api/observatory';
import { qk } from '@/lib/queryClient';

export function useOverview(windowS: number) {
  return useQuery({ queryKey: qk.observatory('overview', windowS), queryFn: () => getOverview(windowS), refetchInterval: 5_000 });
}
export function useQueue() {
  return useQuery({ queryKey: qk.observatory('queue'), queryFn: getQueue, refetchInterval: 5_000 });
}
export function useTraces(query: string) {
  return useQuery({ queryKey: qk.observatory('traces', query), queryFn: () => getTraces(query), refetchInterval: 10_000 });
}
export function useTrace(traceId: string) {
  return useQuery({ queryKey: qk.observatory('trace', traceId), queryFn: () => getTrace(traceId), refetchInterval: 10_000 });
}
export function useLogs(query: string) {
  return useQuery({ queryKey: qk.observatory('logs', query), queryFn: () => getLogs(query), refetchInterval: 10_000 });
}
export function useDatabase(windowS: number) {
  return useQuery({ queryKey: qk.observatory('database', windowS), queryFn: () => getDatabase(windowS), refetchInterval: 10_000 });
}
export function useOperations(windowS: number, component?: string) {
  return useQuery({
    queryKey: qk.observatory('operations', windowS, component ?? ''),
    queryFn: () => getOperations(windowS, component),
    refetchInterval: 15_000,
  });
}
export function useLlm(windowS: number) {
  return useQuery({ queryKey: qk.observatory('llm', windowS), queryFn: () => getLlm(windowS), refetchInterval: 15_000 });
}
export function useAnalysis() {
  return useQuery({ queryKey: qk.observatory('analysis'), queryFn: getAnalysis, refetchInterval: 15_000 });
}
export function useErrors(windowS: number) {
  return useQuery({ queryKey: qk.observatory('errors', windowS), queryFn: () => getErrors(windowS), refetchInterval: 15_000 });
}
export function useClients() {
  return useQuery({ queryKey: qk.observatory('clients'), queryFn: getClients, refetchInterval: 15_000 });
}
export function useSamples(names: string, windowS: number) {
  return useQuery({
    queryKey: qk.observatory('samples', names, windowS),
    queryFn: () => getSamples(names, windowS),
    refetchInterval: 30_000,
  });
}

export function useSystem(windowS: number, traceId: string | undefined, paused: boolean) {
  return useQuery({
    queryKey: qk.observatory('system', windowS, traceId ?? ''),
    queryFn: () => getSystem(windowS, traceId),
    refetchInterval: paused ? false : 10_000,
  });
}

export function useModuleCalls(moduleId: string | undefined, windowS: number, traceId: string | undefined, paused: boolean) {
  return useQuery({
    queryKey: qk.observatory('module-calls', moduleId ?? '', windowS, traceId ?? ''),
    queryFn: () => getModuleCalls(moduleId ?? '', windowS, traceId),
    enabled: Boolean(moduleId),
    refetchInterval: paused ? false : 5_000,
  });
}

export function useInvocation(traceId: string | undefined, spanId: string | undefined, paused: boolean) {
  return useQuery({
    queryKey: qk.observatory('span', traceId ?? '', spanId ?? ''),
    queryFn: () => getInvocation(traceId ?? '', spanId ?? ''),
    enabled: Boolean(traceId && spanId),
    refetchInterval: query => {
      if (paused || !traceId || !spanId) return false;
      const status = query.state.data?.span.status;
      return status === 'running' || status == null ? 1_000 : false;
    },
  });
}

export interface LiveItem { kind: 'span' | 'log'; item: ObsSpanSummary | ObsLog }
export interface LiveArrival {
  trace_id: string;
  span_id: string;
  module_id: string | null;
  parent_module_id: string | null;
  status: ObsSpanSummary['status'];
}

interface LiveSnapshot {
  instance_id: string;
  sequence: number;
  at: string;
  active: ObsSpanSummary[];
  recent: ObsSpanSummary[];
  active_complete?: boolean;
}

const FEED_LIMIT = 500;
const REMEMBERED = 2000;
const QUEUE_CAP = 2000;


function asSpan(value: unknown): ObsSpanSummary {
  const raw = value as Partial<ObsSpanSummary> & { sequence?: number };
  return {
    trace_id: raw.trace_id ?? '',
    span_id: raw.span_id ?? '',
    parent_span_id: raw.parent_span_id ?? null,
    module_id: raw.module_id ?? null,
    parent_module_id: raw.parent_module_id ?? null,
    name: raw.name ?? '',
    component: raw.component ?? '',
    kind: raw.kind ?? '',
    started_at: raw.started_at ?? new Date().toISOString(),
    duration_ms: raw.duration_ms ?? 0,
    self_ms: raw.self_ms ?? null,
    status: raw.status ?? 'running',
    status_message: raw.status_message ?? null,
    attrs: raw.attrs ?? {},
    links: raw.links ?? [],
  };
}

type Queued =
  | { type: 'span' | 'span_start'; span: ObsSpanSummary; sequence: number | null }
  | { type: 'log'; log: ObsLog }
  | { type: 'snapshot'; snapshot: LiveSnapshot }
  | { type: 'health'; health: ObsHealth }
  | { type: 'lagged' };

export function useLive(filters: LiveFilters, paused: boolean) {
  const [items, setItems] = useState<LiveItem[]>([]);
  const [connected, setConnected] = useState(false);
  const [health, setHealth] = useState<ObsHealth | null>(null);
  const [lagged, setLagged] = useState(false);
  const [missedWhilePaused, setMissed] = useState(0);
  const [active, setActive] = useState<ObsSpanSummary[]>([]);
  const [instanceId, setInstanceId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [arrived, setArrived] = useState<LiveArrival[]>([]);
  const [generation, setGeneration] = useState(0);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;
  const wasPaused = useRef(paused);
  const watermark = useRef(0);
  const remembered = useRef<string[]>([]);
  const queue = useRef<Queued[]>([]);
  const timer = useRef<number | null>(null);
  const activeRef = useRef<Map<string, ObsSpanSummary>>(new Map());
  const itemsRef = useRef<LiveItem[]>([]);

  useEffect(() => {
    if (wasPaused.current && !paused) {
      setMissed(0);
      setGeneration(value => value + 1);
    }
    wasPaused.current = paused;
  }, [paused]);

  useEffect(() => {
    const source = new EventSource(liveUrl(filters));
    const remember = (key: string) => {
      remembered.current.push(key);
      if (remembered.current.length > REMEMBERED) remembered.current.splice(0, remembered.current.length - REMEMBERED);
    };
    const flush = () => {
      timer.current = null;
      const batch = queue.current;
      queue.current = [];
      if (batch.length === 0) return;
      const arrivals: LiveArrival[] = [];
      const rememberedSet = new Set(remembered.current);
      let itemsChanged = false;
      let activeChanged = false;
      for (const event of batch) {
        if (event.type === 'health') {
          setHealth(event.health);
          continue;
        }
        if (event.type === 'lagged') {
          setLagged(true);
          continue;
        }
        if (event.type === 'snapshot') {
          watermark.current = event.snapshot.sequence;
          setInstanceId(event.snapshot.instance_id);
          setReady(true);
          setLagged(false);
          activeRef.current = new Map((event.snapshot.active ?? []).map(span => [`${span.trace_id}:${span.span_id}`, asSpan(span)]));
          activeChanged = true;
          const seeded = (event.snapshot.recent ?? []).map(span => ({ kind: 'span' as const, item: asSpan(span) }));
          remembered.current = [];
          for (const row of seeded) remember(`${row.item.trace_id}:${row.item.span_id}`);
          itemsRef.current = seeded.slice(-FEED_LIMIT);
          itemsChanged = true;
          continue;
        }
        if ((event.type === 'span' || event.type === 'span_start') && event.sequence != null && event.sequence <= watermark.current) continue;
        if (event.type === 'span_start') {
          activeRef.current.set(`${event.span.trace_id}:${event.span.span_id}`, { ...event.span, status: 'running' });
          activeChanged = true;
          continue;
        }
        if (event.type === 'log') {
          itemsRef.current = [...itemsRef.current, { kind: 'log' as const, item: event.log }].slice(-FEED_LIMIT);
          itemsChanged = true;
          continue;
        }
        const key = `${event.span.trace_id}:${event.span.span_id}`;
        activeRef.current.delete(key);
        activeChanged = true;
        if (rememberedSet.has(key)) continue;
        rememberedSet.add(key);
        remember(key);
        arrivals.push({
          trace_id: event.span.trace_id,
          span_id: event.span.span_id,
          module_id: event.span.module_id,
          parent_module_id: event.span.parent_module_id,
          status: event.span.status,
        });
        itemsRef.current = [...itemsRef.current.filter(row => row.kind !== 'span' || `${(row.item as ObsSpanSummary).trace_id}:${(row.item as ObsSpanSummary).span_id}` !== key), { kind: 'span' as const, item: event.span }].slice(-FEED_LIMIT);
        itemsChanged = true;
      }
      if (itemsChanged) setItems(itemsRef.current);
      if (activeChanged) setActive([...activeRef.current.values()]);
      setArrived(arrivals);
    };
    const enqueue = (event: Queued) => {
      if (queue.current.length >= QUEUE_CAP) {
        queue.current = [];
        setLagged(true);
        setGeneration(value => value + 1);
        return;
      }
      queue.current.push(event);
      if (timer.current == null) timer.current = window.setTimeout(flush, 250);
    };
    source.onopen = () => setConnected(true);
    source.onerror = () => {
      setConnected(false);
      setReady(false);
    };
    const sequenceOf = (value: unknown): number | null => {
      if (!value || typeof value !== 'object' || !('sequence' in value)) return null;
      return typeof value.sequence === 'number' ? value.sequence : null;
    };
    const onSpan = (event: Event) => {
      const parsed = JSON.parse((event as MessageEvent).data) as unknown;
      if (pausedRef.current) {
        setMissed(count => count + 1);
        return;
      }
      enqueue({ type: 'span', span: asSpan(parsed), sequence: sequenceOf(parsed) });
    };
    const onStart = (event: Event) => {
      const parsed = JSON.parse((event as MessageEvent).data) as unknown;
      if (pausedRef.current) return;
      enqueue({ type: 'span_start', span: { ...asSpan(parsed), status: 'running' }, sequence: sequenceOf(parsed) });
    };
    const onLog = (event: Event) => {
      const parsed = JSON.parse((event as MessageEvent).data) as ObsLog;
      if (pausedRef.current) {
        setMissed(count => count + 1);
        return;
      }
      enqueue({ type: 'log', log: parsed });
    };
    const onSnapshot = (event: Event) => {
      const parsed = JSON.parse((event as MessageEvent).data) as LiveSnapshot;
      enqueue({ type: 'snapshot', snapshot: parsed });
    };
    const onHealth = (event: Event) => enqueue({ type: 'health', health: JSON.parse((event as MessageEvent).data) as ObsHealth });
    const onLagged = () => {
      setLagged(true);
      setGeneration(value => value + 1);
    };
    source.addEventListener('span', onSpan);
    source.addEventListener('span_start', onStart);
    source.addEventListener('log', onLog);
    source.addEventListener('snapshot', onSnapshot);
    source.addEventListener('health', onHealth);
    source.addEventListener('lagged', onLagged);
    return () => {
      if (timer.current != null) window.clearTimeout(timer.current);
      timer.current = null;
      queue.current = [];
      source.close();
    };
  }, [filters.components, filters.errorsOnly, filters.lifecycle, generation]);

  return { items, connected, health, lagged, missedWhilePaused, active, instanceId, ready, arrived };
}

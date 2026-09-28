import type React from 'react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { ObsModuleNode, ObsSpanSummary, ObsSystemSnapshot } from '@/api/observatory';
import { ErrorState, LoadingState } from '@/components/states';
import { useInvocation, useLive, useModuleCalls, useSystem } from '@/hooks/useObservatory';
import { ms } from '@/lib/obsFormat';
import { Badge, Button, ChoiceGroup, IconButton } from '@/ui';
import { ChevronDown, ChevronUp, SlidersHorizontal, X } from 'lucide-react';
import { GraphLegend, ModuleGraph, type GraphPulse } from './ModuleGraph';
import { ModuleInspector, type InspectorTab } from './ModuleInspector';
import { componentLabel } from './systemGraphLayout';
import graphStyles from './ModuleGraph.module.css';
import styles from './SystemView.module.css';

const WINDOWS = [
  { value: '900', label: '15m' }, { value: '3600', label: '1h' },
  { value: '21600', label: '6h' }, { value: '86400', label: '24h' },
  { value: '604800', label: '7d' }, { value: '1209600', label: '14d' },
] as const;

function isWrapper(span: ObsSpanSummary): boolean {
  return span.name === 'db.connection' || span.module_id === 'db.connection';
}

function useDetailsDismiss(ref: React.RefObject<HTMLDetailsElement | null>) {
  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      const details = ref.current;
      if (!details?.open) return;
      if (!details.contains(event.target as Node)) details.open = false;
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [ref]);
  return (event: React.KeyboardEvent<HTMLDetailsElement>) => {
    if (event.key !== 'Escape') return;
    const details = ref.current;
    if (!details) return;
    event.preventDefault();
    details.open = false;
    (details.querySelector('summary') as HTMLElement | null)?.focus();
  };
}

function CoverageDetails({ coverage, source }: { coverage: ObsSystemSnapshot['coverage']; source: 'database' | 'memory' }) {
  const ref = useRef<HTMLDetailsElement>(null);
  const onKeyDown = useDetailsDismiss(ref);
  const warnings: string[] = [];
  if (!coverage.active_complete) warnings.push('Active coverage is incomplete.');
  if (coverage.unresolved_parent_count > 0) warnings.push(`${coverage.unresolved_parent_count} unresolved parents.`);
  if (coverage.dropped_db_spans > 0 || coverage.dropped_db_fetch_spans > 0) warnings.push('Database activity was capped.');
  return (
    <details ref={ref} className={styles.popoverDetails} onKeyDown={onKeyDown}>
      <summary className={styles.popoverSummary}>
        Coverage{warnings.length > 0 && <Badge tone="caution">{warnings.length}</Badge>}
      </summary>
      <div className={styles.popoverBody}>
        <p className={styles.popoverText}>
          {coverage.retained_since ? `Retained since ${new Date(coverage.retained_since).toLocaleString()}.` : 'Retention start unknown.'}
        </p>
        {source === 'memory' && (
          <p className={styles.popoverText}>Memory since {coverage.memory_since ? new Date(coverage.memory_since).toLocaleString() : 'unknown'}.</p>
        )}
        {warnings.map(warning => <p key={warning} className={styles.popoverText}>{warning}</p>)}
      </div>
    </details>
  );
}

export function SystemView() {
  const [params, setParams] = useSearchParams();
  const [paused, setPaused] = useState(false);
  const [followLatest, setFollowLatest] = useState(false);
  const [reach, setReach] = useState<'all' | 'upstream' | 'downstream'>('all');
  const [connections, setConnections] = useState<'all' | 'observed'>('all');
  const [pulses, setPulses] = useState<GraphPulse[]>([]);
  const [detailPane, setDetailPane] = useState<'map' | 'inspector'>(() => (params.get('module') ? 'inspector' : 'map'));
  const [query, setQuery] = useState('');
  const [layoutWidth, setLayoutWidth] = useState(0);
  const lastPulse = useRef<Record<string, number>>({});
  const picked = useRef<string | null>(null);
  const focusAfterSelect = useRef<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const filtersRef = useRef<HTMLDetailsElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  const windowS = Number(params.get('window') || 3600);
  const component = params.get('component');
  const moduleId = params.get('module');
  const trace = params.get('trace') || undefined;
  const callTrace = params.get('call_trace') || undefined;
  const spanId = params.get('span') || undefined;
  const inspect = params.get('inspect');

  const system = useSystem(windowS, trace, paused);
  const calls = useModuleCalls(moduleId ?? undefined, windowS, trace, paused);
  const invocation = useInvocation(callTrace, spanId, paused);
  const live = useLive({ lifecycle: true }, paused);
  const snapshot = system.data;
  const active = live.connected && live.ready ? live.active : (snapshot?.active ?? []);
  const stale = !live.connected;

  const nodesById = useMemo(() => new Map((snapshot?.nodes ?? []).map(node => [node.id, node])), [snapshot]);
  const moduleNode = moduleId ? nodesById.get(moduleId) ?? null : null;
  const scopeComponent = moduleNode ? moduleNode.component : component;
  const componentsPresent = useMemo(() => new Set((snapshot?.nodes ?? []).map(node => node.component)), [snapshot]);
  const scopeKnown = scopeComponent != null && componentsPresent.has(scopeComponent);
  const effectiveScope = scopeKnown ? scopeComponent : null;
  const unknownComponent = component != null && !scopeKnown;

  const componentOf = (span: ObsSpanSummary) => (
    span.module_id ? nodesById.get(span.module_id)?.component ?? span.component : span.component
  );

  const pushParams = (mutate: (current: URLSearchParams) => void) => {
    setParams(current => { mutate(current); return current; });
  };

  const openOverview = () => pushParams(current => {
    current.delete('component'); current.delete('module'); current.delete('call_trace'); current.delete('span'); current.delete('inspect');
  });

  const openComponent = (id: string) => pushParams(current => {
    current.set('component', id); current.delete('module'); current.delete('call_trace'); current.delete('span'); current.delete('inspect');
  });

  const selectModule = (id: string) => {
    const node = nodesById.get(id);
    pushParams(current => {
      if (node) current.set('component', node.component);
      current.set('module', id);
      current.delete('call_trace'); current.delete('span'); current.delete('inspect');
    });
    setDetailPane('inspector');
    focusAfterSelect.current = id;
  };

  const setCall = (span: ObsSpanSummary, explicit: boolean) => {
    const node = span.module_id ? nodesById.get(span.module_id) : undefined;
    setParams(current => {
      if (span.module_id) current.set('module', span.module_id);
      if (node) current.set('component', node.component);
      current.set('call_trace', span.trace_id);
      current.set('span', span.span_id);
      if (explicit) current.delete('inspect');
      return current;
    }, { replace: true });
    if (explicit) {
      setDetailPane('inspector');
      focusAfterSelect.current = span.module_id ?? null;
    }
  };

  const focusCard = (id: string | null) => {
    if (!id) return;
    const card = document.querySelector(`[data-display-id="module:${CSS.escape(id)}"]`) as HTMLElement | null;
    if (card) card.focus();
    else (document.querySelector('[aria-label="Map viewport"]') as HTMLElement | null)?.focus();
  };

  const closeInspector = () => {
    const target = moduleId;
    pushParams(current => {
      current.delete('module'); current.delete('call_trace'); current.delete('span'); current.delete('inspect');
    });
    requestAnimationFrame(() => focusCard(target));
  };

  const onBack = () => {
    const target = moduleId;
    setDetailPane('map');
    requestAnimationFrame(() => focusCard(target));
  };

  const onFollowTrace = () => {
    if (!callTrace) return;
    setParams(current => { current.set('trace', callTrace); return current; }, { replace: true });
  };

  const onTabChange = (tab: InspectorTab) => {
    setParams(current => {
      if (tab === 'invocation') current.delete('inspect');
      else current.set('inspect', tab);
      return current;
    }, { replace: true });
  };

  useEffect(() => {
    if (!moduleNode || !moduleId) return;
    if (moduleNode.component === component) return;
    setParams(current => { current.set('component', moduleNode.component); return current; }, { replace: true });
  }, [moduleNode, component, moduleId, setParams]);

  useEffect(() => {
    const element = bodyRef.current;
    if (!element) return;
    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        const width = entry.contentRect.width;
        if (width <= 0) continue;
        setLayoutWidth(prev => (Math.abs(prev - width) < 1 ? prev : width));
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => { setFollowLatest(false); }, [moduleId]);

  useEffect(() => {
    const pending = focusAfterSelect.current;
    if (!pending) return;
    focusAfterSelect.current = null;
    const card = document.querySelector(`[data-display-id="module:${CSS.escape(pending)}"]`);
    if (!card || card.getClientRects().length === 0) {
      (document.querySelector('aside[aria-label="Inspector"] h2') as HTMLElement | null)?.focus();
    }
  }, [moduleId, callTrace, spanId]);

  useEffect(() => {
    if (!moduleId || followLatest || picked.current === moduleId) return;
    if (callTrace) {
      picked.current = moduleId;
      return;
    }
    const newest = calls.data?.active[0] ?? calls.data?.recent[0];
    if (!newest) return;
    picked.current = moduleId;
    setCall(newest, false);
  }, [moduleId, calls.data, callTrace, followLatest]);

  useEffect(() => {
    if (!followLatest || !moduleId) return;
    const newest = calls.data?.active[0] ?? live.active.find(span => span.module_id === moduleId) ?? calls.data?.recent[0];
    if (!newest) return;
    if (newest.trace_id === callTrace && newest.span_id === spanId) return;
    setCall(newest, false);
  }, [followLatest, calls.data, live.active, moduleId, callTrace, spanId]);

  useEffect(() => {
    if (paused || live.arrived.length === 0) return;
    const now = Date.now();
    const next: GraphPulse[] = [];
    for (const arrival of live.arrived) {
      if (!arrival.module_id) continue;
      if (trace && arrival.trace_id !== trace) continue;
      const nodeKey = arrival.module_id;
      const edgeKey = arrival.parent_module_id ? `${arrival.parent_module_id}|${arrival.module_id}` : null;
      if (lastPulse.current[nodeKey] && now - lastPulse.current[nodeKey] < 500) continue;
      if (next.length >= 24) break;
      lastPulse.current[nodeKey] = now;
      if (edgeKey) lastPulse.current[edgeKey] = now;
      next.push({ moduleId: arrival.module_id, parentModuleId: arrival.parent_module_id, error: arrival.status === 'error' });
    }
    if (next.length === 0) return;
    setPulses(next);
    const timer = window.setTimeout(() => setPulses([]), 700);
    return () => window.clearTimeout(timer);
  }, [live.arrived, paused, trace]);

  const graphActive = useMemo(
    () => active.filter(span => !trace || span.trace_id === trace),
    [active, trace],
  );

  const pendingEdges = useMemo(() => graphActive.flatMap(span => (
    span.parent_module_id && span.module_id ? [{ source: span.parent_module_id, target: span.module_id }] : []
  )), [graphActive]);

  const drawerSpans = useMemo(() => {
    const inScope = (span: ObsSpanSummary) => (
      (!trace || span.trace_id === trace) && (effectiveScope == null || componentOf(span) === effectiveScope)
    );
    const runningSpans = active.filter(inScope);
    const completedSpans = live.items
      .flatMap(item => (item.kind === 'span' ? [item.item as ObsSpanSummary] : []))
      .filter(inScope)
      .reverse();
    const seen = new Set<string>();
    const rows: ObsSpanSummary[] = [];
    for (const span of [...runningSpans, ...completedSpans]) {
      if (isWrapper(span)) continue;
      const key = `${span.trace_id}:${span.span_id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push(span);
      if (rows.length >= 100) break;
    }
    return rows;
  }, [active, live.items, trace, effectiveScope, nodesById]);

  const searchMatches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return [];
    return (snapshot?.nodes ?? [])
      .map(node => ({ node, label: componentLabel(node.component) }))
      .filter(({ node, label }) => [
        node.id, node.label, node.component, label,
        node.source?.file ?? '', node.source?.symbol ?? '',
        ...node.inputs, ...node.outputs,
      ].some(value => value.toLowerCase().includes(needle)))
      .sort((a, b) => a.label.localeCompare(b.label) || a.node.label.localeCompare(b.node.label));
  }, [query, snapshot]);

  const status = snapshot ? (
    <div className={styles.statusLine}>
      <span>Stats as of {new Date(snapshot.at).toLocaleTimeString()} from {snapshot.source}{snapshot.partial ? ', partial' : ''}.</span>
      <CoverageDetails coverage={snapshot.coverage} source={snapshot.source} />
      {unknownComponent && <span role="status">This component is not in the current map.</span>}
      {paused && (
        <span role="status">View paused; recording continues.{live.missedWhilePaused > 0 ? ` ${live.missedWhilePaused} completed events missed.` : ''}</span>
      )}
      {stale && <span role="status">The map is disconnected and may be stale.</span>}
      {live.lagged && <span role="status">The live stream fell behind. Active calls were replaced from a fresh snapshot.</span>}
      {system.isError && (
        <span role="status">
          The latest map refresh failed.{' '}
          <Button variant="quiet" size="sm" onClick={() => { void system.refetch(); }}>Retry</Button>
        </span>
      )}
    </div>
  ) : null;

  const filtersKeyDown = useDetailsDismiss(filtersRef);

  return (
    <div className={styles.workspace}>
      <div className={styles.toolbar}>
        <nav aria-label="Map location" className={styles.location}>
          {effectiveScope ? (
            <>
              <Button variant="quiet" size="sm" onClick={openOverview}>System</Button>
              <span aria-hidden="true" className={styles.slash}>/</span>
              <span aria-current="page" className={styles.current}>{componentLabel(effectiveScope)}</span>
            </>
          ) : (
            <span aria-current="page" className={styles.current}>System</span>
          )}
        </nav>
        <div className={styles.searchWrap}>
          <input
            ref={inputRef}
            type="search"
            className={styles.searchInput}
            aria-label="Search modules"
            placeholder="Search modules, sources or ports"
            value={query}
            onChange={event => setQuery(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'ArrowDown' && searchMatches.length > 0) {
                event.preventDefault();
                (resultsRef.current?.querySelector('button') as HTMLElement | null)?.focus();
              } else if (event.key === 'Escape' && query) {
                event.preventDefault();
                setQuery('');
              }
            }}
          />
          {query.trim() && (
            <div className={styles.searchPanel} ref={resultsRef} onKeyDown={event => {
              const buttons = Array.from(resultsRef.current?.querySelectorAll('button') ?? []) as HTMLElement[];
              const index = buttons.indexOf(document.activeElement as HTMLElement);
              if (event.key === 'ArrowDown') {
                event.preventDefault();
                buttons[index + 1]?.focus();
              } else if (event.key === 'ArrowUp') {
                event.preventDefault();
                if (index <= 0) inputRef.current?.focus();
                else buttons[index - 1]?.focus();
              } else if (event.key === 'Escape') {
                event.preventDefault();
                inputRef.current?.focus();
              }
            }}>
              {searchMatches.length === 0
                ? <p className={styles.searchEmpty}>No modules match.</p>
                : searchMatches.map(({ node, label }) => (
                  <button
                    key={node.id}
                    type="button"
                    className={styles.searchResult}
                    onClick={() => { selectModule(node.id); setQuery(''); }}
                  >
                    <span className={styles.searchLabel}>{node.label}</span>
                    <span className={styles.searchMeta}>{node.id}, {label}</span>
                  </button>
                ))}
            </div>
          )}
        </div>
        <label className={styles.windowLabel}><span className={styles.narrowHidden}>Window</span>
          <select
            className={styles.windowSelect}
            value={String(windowS)}
            onChange={event => {
              setParams(current => { current.set('window', event.target.value); return current; }, { replace: true });
            }}
          >
            {WINDOWS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <details ref={filtersRef} className={`${styles.popoverDetails} ${styles.filters}`} onKeyDown={filtersKeyDown}>
          <summary className={styles.popoverSummary}><SlidersHorizontal /><span className={styles.narrowHidden}>Filters</span></summary>
          <div className={styles.popoverBody}>
            <ChoiceGroup
              label="Connections"
              value={connections}
              options={[{ value: 'all', label: 'All connections' }, { value: 'observed', label: 'Observed only' }]}
              onChange={value => { if (value) setConnections(value); }}
            />
            <ChoiceGroup
              label="Reach"
              value={reach}
              disabled={!moduleId}
              options={[{ value: 'all', label: 'All' }, { value: 'upstream', label: 'Upstream' }, { value: 'downstream', label: 'Downstream' }]}
              onChange={value => { if (value) setReach(value); }}
            />
            <div className={styles.filtersLegend}><GraphLegend /></div>
          </div>
        </details>
        {trace && (
          <Button
            size="sm"
            className={styles.traceChip}
            icon={<X />}
            aria-label={`Remove trace filter ${trace}`}
            onClick={() => { setParams(current => { current.delete('trace'); return current; }, { replace: true }); }}
          >
            Trace {trace.slice(0, 8)}
          </Button>
        )}
        <Button size="sm" className={styles.pauseButton} onClick={() => setPaused(value => !value)}>
          {paused ? 'Resume' : 'Pause'}
        </Button>
        <span className={styles.connectionBadge}>
          <Badge tone={stale ? 'caution' : 'better'}>
            {stale ? 'Disconnected' : paused ? 'Paused' : 'Live'}
          </Badge>
        </span>
      </div>
      <div
        ref={bodyRef}
        className={styles.body}
        data-inspector={moduleId ? 'open' : 'closed'}
        data-detail={detailPane}
      >
        <div className={styles.mapColumn}>
          {snapshot ? (
            <ModuleGraph
              nodes={snapshot.nodes}
              edges={snapshot.edges}
              active={graphActive}
              pendingEdges={pendingEdges}
              component={effectiveScope}
              selected={moduleId}
              reach={reach}
              connections={connections}
              pulses={paused ? [] : pulses}
              layoutWidth={layoutWidth}
              status={status}
              onOpenComponent={openComponent}
              onSelect={selectModule}
            />
          ) : system.isError ? (
            <section className={graphStyles.frame} aria-label="System map">
              <div className={graphStyles.emptyHost}>
                <ErrorState message="The system map could not be loaded." onRetry={() => { void system.refetch(); }} />
              </div>
            </section>
          ) : (
            <section className={graphStyles.frame} aria-label="System map">
              <div className={graphStyles.emptyHost}>
                <LoadingState label="Loading the system map…" />
              </div>
            </section>
          )}
          <RecentCallsDrawer spans={drawerSpans} nodesById={nodesById} onSelect={span => setCall(span, true)} />
        </div>
        {moduleId && (
          <aside className={styles.inspector} aria-label="Inspector">
            <ModuleInspector
              node={moduleNode}
              missing={Boolean(moduleId) && Boolean(snapshot) && !moduleNode}
              edges={snapshot?.edges ?? []}
              calls={calls.data}
              callsLoading={calls.isLoading}
              callsError={calls.isError ? 'Module calls are temporarily unavailable.' : undefined}
              onRetryCalls={() => { void calls.refetch(); }}
              invocation={invocation.data}
              selectedCall={Boolean(callTrace && spanId)}
              invocationError={invocation.isError ? 'Invocation details are not currently available.' : undefined}
              onRetryInvocation={() => { void invocation.refetch(); }}
              followLatest={followLatest}
              onFollowLatest={setFollowLatest}
              onSelectCall={span => setCall(span, true)}
              onLatest={() => {
                const newest = calls.data?.active[0] ?? calls.data?.recent[0];
                if (newest) setCall(newest, true);
              }}
              onFollowTrace={onFollowTrace}
              tab={inspect === 'module' || inspect === 'calls' ? inspect : 'invocation'}
              onTabChange={onTabChange}
              onClose={closeInspector}
              onBack={onBack}
            />
          </aside>
        )}
      </div>
    </div>
  );
}

function RecentCallsDrawer({
  spans, nodesById, onSelect,
}: {
  spans: ObsSpanSummary[];
  nodesById: Map<string, ObsModuleNode>;
  onSelect: (span: ObsSpanSummary) => void;
}) {
  const [open, setOpen] = useState(false);
  const listId = `recent-calls-${useId()}`;
  const runningCount = spans.filter(span => span.status === 'running').length;
  return (
    <section aria-label="Recent calls" className={styles.drawer}>
      <div className={styles.drawerHeader}>
        <h2 className={styles.drawerTitle}>Recent calls</h2>
        <span className={styles.drawerCount}>{runningCount} running, {spans.length} shown</span>
        <IconButton
          label={open ? 'Hide recent calls' : 'Show recent calls'}
          icon={open ? <ChevronDown /> : <ChevronUp />}
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen(value => !value)}
        />
      </div>
      <ul id={listId} className={styles.drawerList} hidden={!open}>
        {spans.length === 0 && <li className={styles.drawerEmpty}>No calls in this view.</li>}
        {spans.map(span => {
          const node = span.module_id ? nodesById.get(span.module_id) : undefined;
          const label = node?.label ?? span.module_id ?? span.name;
          return (
            <li key={`${span.trace_id}:${span.span_id}`}>
              <button
                type="button"
                className={styles.drawerRow}
                onClick={() => onSelect(span)}
                title={span.module_id ?? undefined}
              >
                <Badge tone={span.status === 'running' ? 'action' : span.status === 'error' ? 'worse' : 'neutral'}>
                  {span.status === 'running' ? 'Running' : span.status === 'error' ? 'Error' : 'OK'}
                </Badge>
                <span className={styles.drawerName}>{label}</span>
                <span className={styles.drawerModule}>{span.module_id ?? '—'}</span>
                <span className={styles.drawerTime}>{new Date(span.started_at).toLocaleTimeString()}</span>
                <span className={styles.drawerDuration}>{span.status === 'running' ? 'Running' : ms(span.duration_ms)}</span>
                <span className={styles.drawerTrace}>{span.trace_id.slice(0, 8)}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}


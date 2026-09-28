import { useState, type ReactNode } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import type { ObsComponentStatus, ObsLog, ObsOverview, ObsSpanSummary } from '@/api/observatory';
import { LoadingState, EmptyState, ErrorState } from '@/components/states';
import { InvocationDetail } from '@/components/observatory/InvocationDetail';
import {
  useAnalysis, useClients, useDatabase, useErrors, useInvocation, useLlm, useLive, useLogs, useOperations,
  useOverview, useQueue, useSamples, useTrace, useTraces,
} from '@/hooks/useObservatory';
import { ago, bytes, ms, pct } from '@/lib/obsFormat';
import { Badge, Button, ChoiceGroup, DataTable, Field, Section, Stat } from '@/ui';
import { Sparkline } from './Sparkline';
import { SystemMap } from './SystemMap';
import { Waterfall } from './Waterfall';

const WINDOWS = [
  { value: '900', label: '15m' }, { value: '3600', label: '1h' },
  { value: '21600', label: '6h' }, { value: '86400', label: '24h' },
] as const;
const LONG_WINDOWS = [...WINDOWS, { value: '604800', label: '7d' }, { value: '1209600', label: '14d' }] as const;
const COMPONENTS = ['http', 'db', 'queue', 'pipeline', 'engine', 'admission', 'chat', 'voice', 'llm', 'import', 'sensors', 'ideas', 'insights', 'system', 'web', 'android'];

export function stateTone(state: string): 'worse' | 'caution' | 'better' | 'neutral' {
  if (state === 'failing') return 'worse';
  if (state === 'degraded') return 'caution';
  if (state === 'ok') return 'better';
  return 'neutral';
}

export function MemoryBanner({ source }: { source?: string }) {
  if (source !== 'memory') return null;
  return <p role="status">PostgreSQL is unreachable, so this view is built from the last 2,000 operations held in memory.</p>;
}

function RecordingGap({ data, windowS }: { data?: ObsOverview; windowS: number }) {
  const started = data?.recording_since ? Date.parse(data.recording_since) : NaN;
  if (Number.isNaN(started) || started <= Date.now() - windowS * 1000) return null;
  const earlier = (label: string, iso: string | null | undefined) => {
    if (!iso || Date.parse(iso) >= started) return null;
    return `${label} ${ago(iso)}`;
  };
  const prior = [
    earlier('Last journal entry', data?.last_journal_at),
    earlier('Last chat', data?.last_chat_at),
  ].filter(Boolean);
  return (
    <p role="status">
      Recording started {ago(data?.recording_since)}. This window reaches further back, so those hours look idle.
      {prior.length > 0 && ` ${prior.join('. ')}. That use ran before recording, so it has no trace.`}
      {' '}Badges are the last 5 minutes, not this window.
    </p>
  );
}


function QueryBody({ query, children }: { query: { isLoading: boolean; isError: boolean; refetch: () => void }; children: ReactNode }) {
  if (query.isLoading) return <LoadingState label="Gathering the Observatory…" />;
  if (query.isError) return <ErrorState onRetry={() => query.refetch()} />;
  return <>{children}</>;
}

export function OverviewTab() {
  const [params, setParams] = useSearchParams();
  const windowS = Number(params.get('window') || 900);
  const query = useOverview(windowS);
  const data = query.data;
  const attention = (data?.components ?? []).filter(item => item.state === 'failing' || item.state === 'degraded')
    .sort((a, b) => Number(b.state === 'failing') - Number(a.state === 'failing'));
  return (
    <QueryBody query={query}>
      <MemoryBanner source={data?.source} />
      <RecordingGap data={data} windowS={windowS} />
      <ChoiceGroup label="Window" value={String(windowS)} options={[...WINDOWS]}
        onChange={value => { if (value) setParams(current => { current.set('window', value); return current; }); }} />
      {data && <SystemMap components={data.components} edges={data.edges} />}
      <Section title="Needs attention">
        {attention.length === 0 ? <EmptyState title="Nothing needs attention." /> : attention.map(item => (
          <p key={item.id}><Badge tone={stateTone(item.state)}>{item.state}</Badge> {item.label}: {item.reasons.join(' ')}</p>
        ))}
      </Section>
      <DataTable label="Components" rowKey={row => row.id} rows={data?.components ?? []} columns={[
        { key: 'name', header: 'Component', cell: (row: ObsComponentStatus) => <>{row.label} <Badge tone={stateTone(row.state)}>{row.state}</Badge></> },
        { key: 'rate', header: 'Ops/min', numeric: true, cell: row => row.calls > 0 && row.rate_per_min < 0.05 ? '<0.1' : row.rate_per_min.toFixed(1) },
        { key: 'errors', header: 'Errors', numeric: true, cell: row => `${row.errors} (${pct(row.calls ? row.errors / row.calls : 0)})` },
        { key: 'p50', header: 'p50', numeric: true, cell: row => ms(row.p50_ms) },
        { key: 'p95', header: 'p95', numeric: true, cell: row => ms(row.p95_ms) },
        { key: 'self', header: 'Self time', numeric: true, cell: row => ms(row.self_ms_total) },
        { key: 'spark', header: 'Last hour', cell: row => <Sparkline values={row.series.calls} marks={row.series.errors.map(count => count > 0)} label={`${row.label} calls`} /> },
      ]} />
    </QueryBody>
  );
}

export function LiveTab() {
  const [params, setParams] = useSearchParams();
  const [paused, setPaused] = useState(false);
  const component = params.get('component') || '';
  const errorsOnly = params.get('errors') === '1';
  const minMs = Number(params.get('min') || 0);
  const live = useLive({ components: component || undefined, errorsOnly }, paused);
  const rows = live.items.filter(item => {
    if (item.kind !== 'span') return true;
    return (item.item as ObsSpanSummary).duration_ms >= minMs;
  });
  return (
    <div>
      <Field label="Component">
        <select value={component} onChange={event => setParams(current => { current.set('component', event.target.value); return current; })}>
          <option value="">All</option>
          {COMPONENTS.map(id => <option key={id} value={id}>{id}</option>)}
        </select>
      </Field>
      <ChoiceGroup label="Errors" value={errorsOnly ? 'errors' : 'all'} options={[{ value: 'all', label: 'All' }, { value: 'errors', label: 'Errors' }]}
        onChange={value => setParams(current => { current.set('errors', value === 'errors' ? '1' : '0'); return current; })} />
      <Field label="Minimum duration">
        <select value={String(minMs)} onChange={event => setParams(current => { current.set('min', event.target.value); return current; })}>
          <option value="0">Any</option>
          <option value="10">≥10 ms</option>
          <option value="100">≥100 ms</option>
          <option value="1000">≥1 s</option>
        </select>
      </Field>
      <Button onClick={() => setPaused(value => !value)}>{paused ? 'Resume' : 'Pause'}</Button>
      <Badge tone={live.connected ? 'better' : 'caution'}>{live.connected ? 'Live' : 'Reconnecting…'}</Badge>
      {live.lagged && <p>The live stream fell behind and dropped events.</p>}
      {paused && live.missedWhilePaused > 0 && <p>{live.missedWhilePaused} events arrived while paused.</p>}
      <ul>
        {rows.map((row, index) => {
          const item = row.item;
          const trace = 'trace_id' in item ? item.trace_id : null;
          return (
            <li key={`${trace ?? 'log'}-${index}`}>
              <Link to={trace ? `/observatory/traces/${trace}` : '/observatory'}>
                {row.kind === 'span'
                  ? `${(item as ObsSpanSummary).started_at} ${(item as ObsSpanSummary).component} ${(item as ObsSpanSummary).name} ${ms((item as ObsSpanSummary).duration_ms)}`
                  : `${(item as ObsLog).at} ${(item as ObsLog).level} ${(item as ObsLog).message}`}
              </Link>
              {row.kind === 'span' && (item as ObsSpanSummary).status === 'error' && <Badge tone="worse">error</Badge>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function TracesTab() {
  const [params] = useSearchParams();
  const queryString = params.toString();
  const query = useTraces(queryString || 'window=3600');
  const navigate = useNavigate();
  return (
    <QueryBody query={query}>
      <DataTable label="Traces" rowKey={row => row.trace_id} rows={query.data ?? []} columns={[
        { key: 'started', header: 'Started', cell: row => ago(row.started_at) },
        { key: 'name', header: 'Name', cell: row => <button type="button" onClick={() => navigate(`/observatory/traces/${row.trace_id}`)}>{row.name}</button> },
        { key: 'component', header: 'Component', cell: row => row.component },
        { key: 'door', header: 'Door', cell: row => row.door || row.client || '—' },
        { key: 'duration', header: 'Duration', numeric: true, cell: row => ms(row.duration_ms) },
        { key: 'spans', header: 'Spans', numeric: true, cell: row => row.spans },
        { key: 'errors', header: 'Errors', numeric: true, cell: row => row.errors },
        { key: 'db', header: 'DB queries', numeric: true, cell: row => row.db_queries ?? '—' },
        { key: 'llm', header: 'Model calls', numeric: true, cell: row => row.llm_calls ?? '—' },
      ]} />
    </QueryBody>
  );
}

export function TraceView({ traceId }: { traceId: string }) {
  const query = useTrace(traceId);
  const [params, setParams] = useSearchParams();
  const requested = params.get('span');
  const detail = query.data;
  const visible = detail?.spans.some(span => span.span_id === requested) ?? false;
  const selected = requested ?? detail?.spans[0]?.span_id ?? null;
  const invocation = useInvocation(traceId, selected ?? undefined, false);
  const limit = detail?.truncated ? detail.total_spans : 2000;
  return (
    <QueryBody query={query}>
      {detail && (
        <>
          <header>
            <h2>{detail.spans[0]?.name}</h2>
            <p>{ms(detail.spans[0]?.duration_ms)} · {detail.spans[0]?.status} · {detail.spans[0]?.started_at}</p>
            {detail.truncated && <p>Showing {detail.spans.length} of {detail.total_spans} spans.</p>}
            <p>Caused by: {detail.caused_by.map(id => <Link key={id} to={`/observatory/traces/${id}`}>{id.slice(0, 8)}</Link>)}</p>
            <p>Started jobs: {detail.caused.map(id => <Link key={id} to={`/observatory/traces/${id}`}>{id.slice(0, 8)}</Link>)}</p>
          </header>
          <Waterfall spans={detail.spans} selected={visible ? selected : null} onSelect={spanId => setParams(current => { current.set('span', spanId); return current; }, { replace: true })} />
          {requested && !visible && <p role="status">This span is outside the displayed waterfall limit of {limit}. Its detail is still loaded below.</p>}
          <InvocationDetail
            detail={invocation.data}
            error={invocation.isError ? 'Invocation details are not currently available.' : undefined}
            onRetry={() => { void invocation.refetch(); }}
            onSelect={(nextTrace, spanId) => setParams(current => { current.set('span', spanId); return current; })}
          />
        </>
      )}
    </QueryBody>
  );
}

export function OperationsTab() {
  const [params, setParams] = useSearchParams();
  const windowS = Number(params.get('window') || 3600);
  const component = params.get('component') || undefined;
  const query = useOperations(windowS, component);
  return (
    <QueryBody query={query}>
      <ChoiceGroup label="Window" value={String(windowS)} options={[...LONG_WINDOWS]}
        onChange={value => { if (value) setParams(current => { current.set('window', value); return current; }); }} />
      <DataTable label="Operations" rowKey={row => `${row.component}:${row.name}`} rows={query.data ?? []} columns={[
        { key: 'component', header: 'Component', cell: row => row.component },
        { key: 'name', header: 'Operation', cell: row => row.slowest_trace_id ? <Link to={`/observatory/traces/${row.slowest_trace_id}`}>{row.name}</Link> : row.name },
        { key: 'calls', header: 'Calls', numeric: true, cell: row => row.calls },
        { key: 'errors', header: 'Errors', numeric: true, cell: row => row.errors },
        { key: 'p50', header: 'p50', numeric: true, cell: row => ms(row.p50_ms) },
        { key: 'p95', header: 'p95', numeric: true, cell: row => ms(row.p95_ms) },
        { key: 'p99', header: 'p99', numeric: true, cell: row => ms(row.p99_ms) },
        { key: 'max', header: 'Max', numeric: true, cell: row => ms(row.max_ms) },
        { key: 'self', header: 'Self total', numeric: true, cell: row => ms(row.self_ms_total) },
        { key: 'share', header: 'Self share', numeric: true, cell: row => pct(row.self_share) },
      ]} />
    </QueryBody>
  );
}

export function QueueTab() {
  const query = useQueue();
  const samples = useSamples('queue.due,queue.oldest_due_age_s', 3600);
  const data = query.data;
  return (
    <QueryBody query={query}>
      {data && (
        <>
          <Stat label="Due" value={data.counts.due ?? '—'} />
          <Stat label="Leased" value={data.counts.leased ?? '—'} />
          <Stat label="Scheduled retry" value={data.counts.scheduled_retry ?? '—'} />
          <Stat label="Exhausted" value={data.counts.exhausted ?? '—'} />
          <Stat label="Oldest due" value={data.oldest_due_age_s == null ? '—' : `${Math.round(data.oldest_due_age_s)} s`} />
          <Sparkline values={(samples.data?.series['queue.due'] ?? []).map(point => point[1])} label="Queue due" />
          <DataTable label="By source" rowKey={row => row.source_type} rows={data.by_source_type} columns={[
            { key: 'type', header: 'Source', cell: row => row.source_type },
            { key: 'due', header: 'Due', numeric: true, cell: row => row.due },
            { key: 'retry', header: 'Retry', numeric: true, cell: row => row.scheduled_retry },
            { key: 'exhausted', header: 'Exhausted', numeric: true, cell: row => row.exhausted },
          ]} />
          <DataTable label="Items" rowKey={row => String(row.id)} rows={data.items} columns={[
            { key: 'type', header: 'Source', cell: row => row.source_type },
            { key: 'id', header: 'Id', cell: row => row.source_id },
            { key: 'attempts', header: 'Attempts', cell: row => `${row.attempts}×/${row.max_attempts}` },
            { key: 'state', header: 'State', cell: row => <Badge tone={row.state === 'exhausted' ? 'worse' : 'neutral'}>{row.state}</Badge> },
            { key: 'next', header: 'Next', cell: row => ago(row.next_attempt_at) },
            { key: 'created', header: 'Created', cell: row => ago(row.created_at) },
            { key: 'error', header: 'Last error', cell: row => row.last_error ?? '—' },
            { key: 'origin', header: 'Origin', cell: row => row.origin_trace_id ? <Link to={`/observatory/traces/${row.origin_trace_id}`}>trace</Link> : '—' },
          ]} />
        </>
      )}
    </QueryBody>
  );
}

export function DatabaseTab() {
  const [params] = useSearchParams();
  const query = useDatabase(Number(params.get('window') || 3600));
  const data = query.data;
  return (
    <QueryBody query={query}>
      {data && (
        <>
          <Stat label="Pool in use" value={String(data.pool?.in_use ?? '—')} />
          <Stat label="Server active" value={String(data.server?.active ?? '—')} />
          <DataTable label="Activity" rowKey={row => String(row.pid)} rows={data.activity} columns={[
            { key: 'pid', header: 'Pid', cell: row => String(row.pid) },
            { key: 'app', header: 'Application', cell: row => String(row.application_name ?? '') },
            { key: 'state', header: 'State', cell: row => String(row.state ?? '') },
            { key: 'query', header: 'Query', cell: row => <pre style={{ whiteSpace: 'pre-wrap' }}>{String(row.query ?? '')}</pre> },
          ]} />
          <DataTable label="Statements" rowKey={row => String(row.fingerprint)} rows={data.statements} columns={[
            { key: 'summary', header: 'Summary', cell: row => String(row.summary ?? '') },
            { key: 'calls', header: 'Calls', numeric: true, cell: row => String(row.calls ?? '') },
            { key: 'sample', header: 'Sample', cell: row => <pre style={{ whiteSpace: 'pre-wrap' }}>{String(row.sample ?? '')}</pre> },
          ]} />
          <DataTable label="Tables" rowKey={row => String(row.name)} rows={data.tables} columns={[
            { key: 'name', header: 'Table', cell: row => String(row.name) },
            { key: 'size', header: 'Size', numeric: true, cell: row => bytes(Number(row.size_bytes ?? 0)) },
          ]} />
          <Section title="pg_stat_statements">
            {data.pg_stat_statements.available
              ? <DataTable label="pg_stat_statements" rowKey={row => String(row.query)} rows={data.pg_stat_statements.rows ?? []} columns={[
                { key: 'query', header: 'Query', cell: row => <pre style={{ whiteSpace: 'pre-wrap' }}>{String(row.query)}</pre> },
                { key: 'calls', header: 'Calls', numeric: true, cell: row => String(row.calls) },
              ]} />
              : <p>{data.pg_stat_statements.hint}</p>}
          </Section>
        </>
      )}
    </QueryBody>
  );
}

export function LlmTab() {
  const [params, setParams] = useSearchParams();
  const windowS = Number(params.get('window') || 86400);
  const query = useLlm(windowS);
  return (
    <QueryBody query={query}>
      <ChoiceGroup label="Window" value={String(windowS)} options={[...LONG_WINDOWS]}
        onChange={value => { if (value) setParams(current => { current.set('window', value); return current; }); }} />
      <DataTable label="Model groups" rowKey={row => `${row.name}-${row.model}-${row.purpose}`} rows={query.data?.groups ?? []} columns={[
        { key: 'name', header: 'Operation', cell: row => String(row.name ?? '') },
        { key: 'model', header: 'Model', cell: row => String(row.model ?? '') },
        { key: 'purpose', header: 'Purpose', cell: row => String(row.purpose ?? '') },
        { key: 'calls', header: 'Calls', numeric: true, cell: row => String(row.calls ?? '') },
        { key: 'cost', header: 'Cost', numeric: true, cell: row => row.cost_usd == null ? '—' : String(row.cost_usd) },
      ]} />
    </QueryBody>
  );
}

export function AnalysisTab() {
  const query = useAnalysis();
  return (
    <QueryBody query={query}>
      {(query.data?.runs ?? []).map(run => (
        <Section key={String(run.trace_id)} title={String(run.caller ?? 'run')} description={`${ago(String(run.started_at ?? ''))} · ${ms(Number(run.duration_ms ?? 0))}`}>
          <p>Unavailable: {JSON.stringify(run.unavailable ?? [])}</p>
          <DataTable label="Engines" rowKey={row => String(row.name)} rows={(run.engines as Record<string, unknown>[]) ?? []} columns={[
            { key: 'name', header: 'Engine', cell: row => String(row.name) },
            { key: 'duration', header: 'Duration', numeric: true, cell: row => ms(Number(row.duration_ms ?? 0)) },
            { key: 'findings', header: 'Findings', numeric: true, cell: row => String(row.findings ?? '') },
            { key: 'status', header: 'Status', cell: row => String(row.status ?? '') },
          ]} />
          <DataTable label="Gates" rowKey={row => String(row.name)} rows={(run.gates as Record<string, unknown>[]) ?? []} columns={[
            { key: 'name', header: 'Gate', cell: row => String(row.name) },
            { key: 'flow', header: 'In → out', cell: row => `${row.in ?? '—'} → ${row.out ?? '—'}` },
            { key: 'reasons', header: 'Reasons', cell: row => JSON.stringify(row.reasons ?? {}) },
          ]} />
        </Section>
      ))}
    </QueryBody>
  );
}

export function ErrorsTab() {
  const query = useErrors(86400);
  const [level, setLevel] = useState('WARNING');
  const logs = useLogs(`level=${level}&window=86400`);
  return (
    <QueryBody query={query}>
      <DataTable label="Grouped errors" rowKey={row => `${row.source}-${row.name}-${row.message}`} rows={query.data?.groups ?? []} columns={[
        { key: 'source', header: 'Source', cell: row => `${row.source ?? ''} ${row.component ?? ''}` },
        { key: 'name', header: 'Name', cell: row => String(row.name ?? '') },
        { key: 'type', header: 'Type', cell: row => String(row.error_type ?? '') },
        { key: 'message', header: 'Message', cell: row => String(row.message ?? '') },
        { key: 'count', header: 'Count', numeric: true, cell: row => String(row.count ?? '') },
        { key: 'trace', header: 'Sample', cell: row => row.sample_trace_id ? <Link to={`/observatory/traces/${row.sample_trace_id}`}>trace</Link> : '—' },
      ]} />
      <Field label="Minimum level">
        <select value={level} onChange={event => setLevel(event.target.value)}>
          {['DEBUG', 'INFO', 'WARNING', 'ERROR'].map(item => <option key={item}>{item}</option>)}
        </select>
      </Field>
      <ul>{(logs.data ?? []).map((log, index) => <li key={index}>{log.level} {log.logger} {log.message}</li>)}</ul>
    </QueryBody>
  );
}

export function ClientsTab() {
  const query = useClients();
  const data = query.data;
  return (
    <QueryBody query={query}>
      {data && (
        <>
          <Section title="Web">
            <p>Last seen {ago(String(data.web.last_seen ?? ''))}. Requests {String(data.web.requests ?? 0)}. Errors {String(data.web.errors ?? 0)}. p95 {ms(Number(data.web.p95_ms ?? 0))}.</p>
          </Section>
          <Section title="Android">
            <p>Last seen {ago(String(data.android.last_seen ?? ''))}.</p>
            <Stat label="Waiting payloads" value={String((data.android.state as { state?: { collector?: { waiting_payloads?: number } } } | null)?.state?.collector?.waiting_payloads ?? '—')} />
          </Section>
          <Section title="Phone"><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(data.phone, null, 2)}</pre></Section>
          <Section title="Listeners"><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(data.listeners, null, 2)}</pre></Section>
        </>
      )}
    </QueryBody>
  );
}

/**
 * Observatory reads. Types live here the way settings types live in api/settings.ts.
 */

import { api } from '@/api/client';

const BASE = (import.meta.env.VITE_BACKEND_URL ?? '') as string;

export interface ObsSpanSummary {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  module_id: string | null;
  parent_module_id: string | null;
  name: string;
  component: string;
  kind: string;
  started_at: string;
  duration_ms: number;
  self_ms: number | null;
  status: 'running' | 'ok' | 'error';
  status_message: string | null;
  attrs: Record<string, unknown>;
  links: { trace_id: string; span_id: string }[];
}

export interface ObsTraceDetail {
  trace_id: string;
  spans: ObsSpanSummary[];
  total_spans: number;
  truncated: boolean;
  logs: ObsLog[];
  caused_by: string[];
  caused: string[];
}

export interface ObsLog {
  at: string;
  source: string;
  level: string;
  logger: string;
  message: string;
  exception: string | null;
  trace_id: string | null;
  span_id: string | null;
  attributes: Record<string, unknown>;
}

export interface ObsComponentStatus {
  id: string;
  label: string;
  state: 'idle' | 'ok' | 'degraded' | 'failing';
  reasons: string[];
  calls: number;
  errors: number;
  rate_per_min: number;
  p50_ms: number | null;
  p95_ms: number | null;
  self_ms_total: number;
  series: { minute: string[]; calls: number[]; errors: number[]; p95_ms: (number | null)[] };
}

export interface ObsEdge { source: string; target: string; calls: number; errors: number; p95_ms: number | null }
export interface ObsOverview {
  generated_at: string;
  window_s: number;
  source: 'database' | 'memory';
  recording_since?: string | null;
  last_journal_at?: string | null;
  last_chat_at?: string | null;
  components: ObsComponentStatus[];
  edges: ObsEdge[];
  probe: Record<string, unknown> | null;
}
export interface ObsTraceSummary {
  trace_id: string; started_at: string; name: string; component: string; duration_ms: number;
  status: string; status_message: string | null; spans: number; errors: number;
  door: string | null; client: string | null; db_queries: number | null; llm_calls: number | null;
}
export interface ObsIOPart {
  label: string;
  state: 'captured' | 'metadata_only' | 'pending' | 'not_captured';
  format: 'text' | 'json';
  text: string | null;
  truncated: boolean | null;
  partial: boolean;
  reason: string | null;
}
export interface ObsModuleNode {
  id: string;
  component: string;
  label: string;
  source: { file: string; symbol: string; line: number | null } | null;
  inputs: string[];
  outputs: string[];
  kind: 'operation' | 'route' | 'table' | 'client' | 'state';
  signature: string | null;
  stats: {
    calls: number; errors: number; rate_per_min: number;
    p50_ms: number | null; p95_ms: number | null; self_ms_total: number;
    last_seen: string | null;
  } | null;
  active: number;
  latest_state: { received_at: string; value: object } | null;
}
export interface ObsModuleEdge {
  source: string;
  target: string;
  kind: 'call' | 'causal' | 'flow';
  evidence: 'declared' | 'observed' | 'both';
  calls: number | null;
  errors: number | null;
  p95_ms: number | null;
}
export interface ObsSystemSnapshot {
  at: string;
  window_s: number;
  trace_id: string | null;
  source: 'database' | 'memory';
  partial: boolean;
  coverage: {
    retained_since: string | null;
    memory_since: string | null;
    unresolved_parent_count: number;
    active_complete: boolean;
    dropped_db_spans: number;
    dropped_db_fetch_spans: number;
  };
  nodes: ObsModuleNode[];
  edges: ObsModuleEdge[];
  active: ObsSpanSummary[];
}
export interface ObsModuleCalls {
  module_id: string;
  at: string;
  source: 'database' | 'memory';
  partial: boolean;
  active: ObsSpanSummary[];
  recent: ObsSpanSummary[];
}
export interface ObsInvocationDetail {
  span: ObsSpanSummary;
  io: { inputs: ObsIOPart[]; outputs: ObsIOPart[] };
  attributes: Record<string, unknown>;
  events: { name: string; at: string; attributes: Record<string, unknown> }[];
  logs: ObsLog[];
  related: ObsSpanSummary[];
  source: 'memory' | 'database';
}
export interface ObsOperation {
  component: string; name: string; calls: number; errors: number;
  p50_ms: number | null; p95_ms: number | null; p99_ms: number | null; max_ms: number | null;
  total_ms: number; self_ms_total: number; self_share: number;
  last_error: string | null; slowest_trace_id: string | null;
}
export interface ObsQueueView {
  counts: { due: number | null; leased: number | null; scheduled_retry: number | null; exhausted: number | null; total: number | null };
  oldest_due_age_s: number | null;
  by_source_type: { source_type: string; due: number; scheduled_retry: number; exhausted: number }[];
  items: {
    id: number; source_type: string; source_id: number; attempts: number; max_attempts: number;
    state: string; next_attempt_at: string | null; created_at: string | null; last_error: string | null;
    origin_trace_id: string | null;
  }[];
  recent_jobs: ObsSpanSummary[];
  backoff_s: number[];
  max_attempts: number;
}
export interface ObsDatabaseView {
  pool: Record<string, unknown> | null;
  server: Record<string, unknown> | null;
  activity: Record<string, unknown>[];
  statements: Record<string, unknown>[];
  tables: Record<string, unknown>[];
  pg_stat_statements: { available: boolean; hint?: string; rows?: Record<string, unknown>[] };
}
export interface ObsLlmView {
  window_s: number;
  groups: Record<string, unknown>[];
  recent: ObsSpanSummary[];
}
export interface ObsAnalysisView { runs: Record<string, unknown>[] }
export interface ObsErrorsView { window_s: number; groups: Record<string, unknown>[] }
export interface ObsClientsView { web: Record<string, unknown>; android: Record<string, unknown>; phone: unknown; listeners: unknown }
export interface ObsHealth {
  generated_at: string;
  source: string;
  components: { id: string; state: string; reasons: string[] }[];
}
export interface LiveFilters { components?: string; errorsOnly?: boolean; lifecycle?: boolean }

export function getOverview(windowS: number): Promise<ObsOverview> {
  return api.get(`/observatory/overview?window=${windowS}`);
}
export function getTraces(query: string): Promise<ObsTraceSummary[]> {
  return api.get(`/observatory/traces?${query}`);
}
export function getTrace(traceId: string): Promise<ObsTraceDetail> {
  return api.get(`/observatory/traces/${traceId}`);
}
export function getOperations(windowS: number, component?: string): Promise<ObsOperation[]> {
  const extra = component ? `&component=${encodeURIComponent(component)}` : '';
  return api.get(`/observatory/operations?window=${windowS}${extra}`);
}
export function getQueue(): Promise<ObsQueueView> { return api.get('/observatory/queue'); }
export function getDatabase(windowS: number): Promise<ObsDatabaseView> {
  return api.get(`/observatory/database?window=${windowS}`);
}
export function getLlm(windowS: number): Promise<ObsLlmView> {
  return api.get(`/observatory/llm?window=${windowS}`);
}
export function getAnalysis(): Promise<ObsAnalysisView> { return api.get('/observatory/analysis'); }
export function getErrors(windowS: number): Promise<ObsErrorsView> {
  return api.get(`/observatory/errors?window=${windowS}`);
}
export function getLogs(query: string): Promise<ObsLog[]> { return api.get(`/observatory/logs?${query}`); }
export function getSamples(names: string, windowS: number): Promise<{ series: Record<string, [string, number][]> }> {
  return api.get(`/observatory/samples?names=${encodeURIComponent(names)}&window=${windowS}`);
}
export function getClients(): Promise<ObsClientsView> { return api.get('/observatory/clients'); }
export function getSystem(windowS: number, traceId?: string): Promise<ObsSystemSnapshot> {
  const params = new URLSearchParams({ window: String(windowS) });
  if (traceId) params.set('trace_id', traceId);
  return api.get(`/observatory/system?${params}`);
}
export function getModuleCalls(moduleId: string, windowS: number, traceId?: string): Promise<ObsModuleCalls> {
  const params = new URLSearchParams({ module_id: moduleId, window: String(windowS) });
  if (traceId) params.set('trace_id', traceId);
  return api.get(`/observatory/module-calls?${params}`);
}
export function getInvocation(traceId: string, spanId: string): Promise<ObsInvocationDetail> {
  return api.get(`/observatory/spans/${traceId}/${spanId}`);
}
export function liveUrl(filters: LiveFilters): string {
  const params = new URLSearchParams();
  if (filters.components) params.set('components', filters.components);
  if (filters.errorsOnly) params.set('errors_only', 'true');
  if (filters.lifecycle) params.set('lifecycle', 'true');
  return `${BASE}/api/observatory/live?${params}`;
}

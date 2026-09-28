/**
 * Browser spans and errors for the Observatory. Does not import client.ts:
 * that module imports this one.
 */

const BASE = (import.meta.env.VITE_BACKEND_URL ?? '') as string;
export const TELEMETRY_PATH = '/api/observatory/client-events';
const CAP = 500;

export interface ClientSpan {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  started_at_ms: number;
  duration_ms: number;
  status: 'ok' | 'error';
  status_message: string | null;
  attributes: Record<string, string | number | boolean | null>;
}

export interface ClientLog {
  at_ms: number;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  message: string;
  exception: string | null;
  trace_id: string | null;
  span_id: string | null;
  attributes: Record<string, string | number | boolean | null>;
}

const spans: ClientSpan[] = [];
const logs: ClientLog[] = [];
let installed = false;
let timer: ReturnType<typeof setInterval> | undefined;

function hex(bytes: number): string {
  const buffer = new Uint8Array(bytes);
  crypto.getRandomValues(buffer);
  return [...buffer].map(byte => byte.toString(16).padStart(2, '0')).join('');
}

export function newTrace(): { traceId: string; spanId: string; traceparent: string } {
  const traceId = hex(16);
  const spanId = hex(8);
  return { traceId, spanId, traceparent: `00-${traceId}-${spanId}-01` };
}

export function routeName(method: string, path: string): string {
  const named = path.split('/').map(segment => {
    if (!segment) return segment;
    if (/^\d+$/.test(segment) || (/\d/.test(segment) && segment.length >= 6)) return '{id}';
    return segment;
  }).join('/');
  return `${method} ${named}`;
}

function push<T>(buffer: T[], item: T): void {
  buffer.push(item);
  if (buffer.length > CAP) buffer.splice(0, buffer.length - CAP);
}

export function tracedRequest(method: string, path: string): {
  headers: Record<string, string>;
  finish: (status: number, error?: string, extra?: Record<string, string | number | boolean | null>) => void;
} {
  if (path.startsWith('/observatory/')) {
    return { headers: {}, finish: () => {} };
  }
  const trace = newTrace();
  const started = Date.now();
  const mark = performance.now();
  return {
    headers: { traceparent: trace.traceparent, 'X-Iris-Client': 'web' },
    finish(status, error, extra) {
      push(spans, {
        trace_id: trace.traceId,
        span_id: trace.spanId,
        parent_span_id: null,
        name: routeName(method, `/api${path}`),
        started_at_ms: started,
        duration_ms: performance.now() - mark,
        status: status === 0 || status >= 500 ? 'error' : 'ok',
        status_message: error ?? null,
        attributes: {
          'http.response.status_code': status,
          'iris.client.route': typeof location === 'undefined' ? '' : location.pathname,
          ...extra,
        },
      });
    },
  };
}

export function recordError(
  message: string,
  error?: unknown,
  attributes?: Record<string, string | number | boolean | null>,
): void {
  const stack = error instanceof Error ? error.stack ?? error.message : error == null ? null : String(error);
  push(logs, {
    at_ms: Date.now(),
    level: 'ERROR',
    message,
    exception: stack,
    trace_id: null,
    span_id: null,
    attributes: attributes ?? {},
  });
}

function payload(): string {
  return JSON.stringify({ source: 'web', spans, logs });
}

function restore(sentSpans: ClientSpan[], sentLogs: ClientLog[]): void {
  spans.unshift(...sentSpans);
  logs.unshift(...sentLogs);
  if (spans.length > CAP) spans.splice(0, spans.length - CAP);
  if (logs.length > CAP) logs.splice(0, logs.length - CAP);
}

export async function flush(options: { beacon?: boolean } = {}): Promise<void> {
  if (spans.length === 0 && logs.length === 0) return;
  const sentSpans = spans.splice(0, spans.length);
  const sentLogs = logs.splice(0, logs.length);
  const body = JSON.stringify({ source: 'web', spans: sentSpans, logs: sentLogs });
  const url = `${BASE}${TELEMETRY_PATH}`;
  if (options.beacon && typeof navigator !== 'undefined' && navigator.sendBeacon) {
    navigator.sendBeacon(url, new Blob([body], { type: 'application/json' }));
    return;
  }
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
      credentials: 'include',
    });
    if (!response.ok) restore(sentSpans, sentLogs);
  } catch {
    restore(sentSpans, sentLogs);
  }
}

export function install(): void {
  if (installed || typeof window === 'undefined') return;
  installed = true;
  window.addEventListener('error', event => {
    recordError(event.message || 'window error', event.error);
  });
  window.addEventListener('unhandledrejection', event => {
    recordError('unhandled rejection', event.reason);
  });
  const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
  if (nav) {
    const trace = newTrace();
    push(spans, {
      trace_id: trace.traceId,
      span_id: trace.spanId,
      parent_span_id: null,
      name: 'page.load',
      started_at_ms: Date.now() - nav.duration,
      duration_ms: nav.duration,
      status: 'ok',
      status_message: null,
      attributes: {
        dom_content_loaded_ms: nav.domContentLoadedEventEnd,
        transfer_size: nav.transferSize,
      },
    });
  }
  timer = setInterval(() => { void flush(); }, 10_000);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') void flush({ beacon: true });
  });
}

export function _pendingForTests(): { spans: number; logs: number } {
  return { spans: spans.length, logs: logs.length };
}

void payload;
void timer;

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { ObsOverview, ObsTraceDetail } from '@/api/observatory';

const state = vi.hoisted(() => ({
  overview: undefined as ObsOverview | undefined,
  trace: undefined as ObsTraceDetail | undefined,
}));

vi.mock('@/api/observatory', () => ({
  getOverview: () => Promise.resolve(state.overview),
  getTrace: () => Promise.resolve(state.trace),
  getInvocation: () => Promise.resolve({
    span: state.trace?.spans[0],
    io: { inputs: [], outputs: [] },
    attributes: {},
    events: [],
    logs: [],
    related: [],
    source: 'database',
  }),
  getSystem: () => Promise.resolve(null),
  getModuleCalls: () => Promise.resolve(null),
  liveUrl: (filters?: { lifecycle?: boolean }) => `/api/observatory/live${filters?.lifecycle ? '?lifecycle=true' : ''}`,
  getTraces: () => Promise.resolve([]),
  getOperations: () => Promise.resolve([]),
  getQueue: () => Promise.resolve(null),
  getDatabase: () => Promise.resolve(null),
  getLlm: () => Promise.resolve(null),
  getAnalysis: () => Promise.resolve({ runs: [] }),
  getErrors: () => Promise.resolve({ window_s: 86400, groups: [] }),
  getLogs: () => Promise.resolve([]),
  getSamples: () => Promise.resolve({ series: {} }),
  getClients: () => Promise.resolve(null),
}));

import { ObservatoryScreen } from './ObservatoryScreen';

function show(path = '/observatory') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/observatory" element={<ObservatoryScreen />} />
          <Route path="/observatory/traces/:traceId" element={<ObservatoryScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Observatory', () => {
  it('shows a failing queue reason', async () => {
    state.overview = {
      generated_at: '2026-07-01T00:00:00.000000Z', window_s: 900, source: 'database', edges: [], probe: null,
      components: [{
        id: 'queue', label: 'Ingest queue', state: 'failing',
        reasons: ['1 item gave up after 7 attempts'],
        calls: 0, errors: 0, rate_per_min: 0, p50_ms: null, p95_ms: null, self_ms_total: 0,
        series: { minute: [], calls: [], errors: [], p95_ms: [] },
      }],
    };
    show();
    expect(await screen.findByText(/gave up after 7 attempts/)).toBeInTheDocument();
  });

  it('nests a child span under its parent', async () => {
    state.trace = {
      trace_id: 'a'.repeat(32), caused_by: [], caused: [], logs: [], total_spans: 2, truncated: false,
      spans: [
        { trace_id: 'a'.repeat(32), span_id: 'b'.repeat(16), parent_span_id: null, module_id: 'http:POST /api/journal', parent_module_id: null, name: 'POST /api/journal', component: 'http', kind: 'server', started_at: '2026-07-01T00:00:00.000Z', duration_ms: 40, self_ms: 10, status: 'ok', status_message: null, attrs: {}, links: [] },
        { trace_id: 'a'.repeat(32), span_id: 'c'.repeat(16), parent_span_id: 'b'.repeat(16), module_id: 'pipeline.run', parent_module_id: 'http:POST /api/journal', name: 'pipeline.run', component: 'pipeline', kind: 'internal', started_at: '2026-07-01T00:00:00.010Z', duration_ms: 20, self_ms: 20, status: 'ok', status_message: null, attrs: {}, links: [] },
      ],
    };
    show(`/observatory/traces/${'a'.repeat(32)}`);
    const child = await screen.findByText(/pipeline.run/);
    expect(child.closest('button')?.getAttribute('data-depth')).toBe('1');
    expect(child.closest('button')).toHaveStyle({ paddingLeft: '24px' });
  });

  it('renders a span delivered on the live stream', async () => {
    class FakeEventSource {
      static last: FakeEventSource;
      listeners = new Map<string, (event: MessageEvent) => void>();
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(public url: string) { FakeEventSource.last = this; }
      addEventListener(type: string, fn: (event: MessageEvent) => void) { this.listeners.set(type, fn); }
      close() {}
    }
    vi.stubGlobal('EventSource', FakeEventSource);
    state.overview = { ...state.overview!, components: [] };
    show('/observatory?view=live');
    await waitFor(() => expect(FakeEventSource.last).toBeTruthy());
    FakeEventSource.last.onopen?.();
    FakeEventSource.last.listeners.get('span')?.(new MessageEvent('span', {
      data: JSON.stringify({
        trace_id: 'd'.repeat(32), span_id: 'e'.repeat(16), parent_span_id: null,
        module_id: null, parent_module_id: null, links: [],
        name: 'POST /api/journal', component: 'http', kind: 'server', started_at: '2026-07-01T00:00:00Z',
        duration_ms: 12, self_ms: 12, status: 'ok', status_message: null, attrs: {},
      }),
    }));
    expect(await screen.findByText(/POST \/api\/journal/)).toBeInTheDocument();
  });
});

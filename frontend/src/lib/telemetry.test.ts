import { afterEach, describe, expect, it, vi } from 'vitest';
import { flush, routeName, tracedRequest, _pendingForTests } from './telemetry';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('web telemetry', () => {
  it('sends a traceparent and records a normalised span', async () => {
    const seen: { headers?: Record<string, string>; body?: string } = {};
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init: RequestInit) => {
      seen.body = String(init.body);
      return new Response('{"accepted":1}', { status: 200 });
    }));
    const traced = tracedRequest('GET', '/patterns/abc123');
    expect(traced.headers.traceparent).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/);
    expect(traced.headers['X-Iris-Client']).toBe('web');
    traced.finish(200);
    await flush();
    const body = JSON.parse(seen.body ?? '{}') as { spans: { trace_id: string; name: string }[] };
    expect(body.spans[0].trace_id).toBe(traced.headers.traceparent.slice(3, 35));
    expect(body.spans[0].name).toBe('GET /api/patterns/{id}');
    expect(routeName('GET', '/api/patterns/abc123')).toBe('GET /api/patterns/{id}');
  });

  it('does not record observatory reads', async () => {
    const traced = tracedRequest('GET', '/observatory/overview');
    expect(traced.headers).toEqual({});
    traced.finish(200);
    expect(_pendingForTests().spans).toBe(0);
  });

  it('keeps items when the flush fails and caps the buffer at 500', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('down'); }));
    tracedRequest('GET', '/journal').finish(200);
    await flush();
    expect(_pendingForTests().spans).toBe(1);
    for (let i = 0; i < 520; i += 1) tracedRequest('GET', `/ideas/${100000 + i}`).finish(200);
    expect(_pendingForTests().spans).toBe(500);
  });
});

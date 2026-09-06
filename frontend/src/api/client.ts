/**
 * API client — wraps fetch with auth, JSON handling, error normalization,
 * and a global mock switch for offline frontend dev.
 *
 * Backend team: this is where you wire base URL, auth headers, and any
 * cookie/CSRF handling. Per-domain calls (chat, habits, etc.) sit on top.
 */

import type { ApiError } from '@/types/api';

const BASE = (import.meta.env.VITE_BACKEND_URL ?? '') as string;

export const useMocks = (): boolean =>
  String(import.meta.env.VITE_USE_MOCKS ?? '').toLowerCase() === 'true';

class HttpError extends Error {
  status: number;
  api: ApiError;
  constructor(status: number, api: ApiError) {
    super(api.message);
    this.status = status;
    this.api = api;
  }
}

async function request<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    credentials: 'include',
    body: body == null ? undefined : JSON.stringify(body),
  });

  if (!res.ok) {
    let payload: ApiError;
    try { payload = await res.json(); }
    catch { payload = { code: 'unknown', message: res.statusText }; }
    throw new HttpError(res.status, payload);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get:    <T>(path: string)                 => request<T>('GET',    path),
  post:   <T>(path: string, body?: unknown) => request<T>('POST',   path, body),
  patch:  <T>(path: string, body?: unknown) => request<T>('PATCH',  path, body),
  del:    <T>(path: string)                 => request<T>('DELETE', path),
};

/**
 * Stream Server-Sent Events from a path (used for Mira's chat replies).
 * Yields each event payload as it arrives. Caller is responsible for breaking.
 *
 * Backend should emit `event: token` events with JSON `{ text: string }`
 * and a final `event: done` event with `{ messageId: string }`.
 */
export async function* sse<T = unknown>(path: string, body: unknown): AsyncGenerator<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    credentials: 'include',
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) throw new Error(`SSE failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const data = block
        .split('\n')
        .filter(l => l.startsWith('data:'))
        .map(l => l.slice(5).trim())
        .join('');
      if (data) yield JSON.parse(data) as T;
    }
  }
}

export { HttpError };

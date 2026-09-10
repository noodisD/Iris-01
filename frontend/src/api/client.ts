/**
 * API client — wraps fetch with auth, JSON handling, error normalization,
 * and a global mock switch for offline frontend dev.
 *
 * Backend team: this is where you wire base URL, auth headers, and any
 * cookie/CSRF handling. Per-domain calls (chat, habits, etc.) sit on top.
 */

import type { ApiError } from '@/types/api';

const BASE = (import.meta.env.VITE_BACKEND_URL ?? '') as string;

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

/**
 * Multipart upload, with progress.
 *
 * XMLHttpRequest rather than fetch, deliberately: no shipping browser reports
 * request-upload progress from fetch, and an import can be a 200 MB export, so
 * "uploading…" with no indication of how far is not good enough.
 *
 * Note what is *not* set — Content-Type. The browser has to write it itself
 * because it alone knows the multipart boundary it generated; setting it by
 * hand is the classic way to get a 400 the server cannot explain.
 *
 * Errors are normalised into the same HttpError/ApiError shape as request(), so
 * callers do not need to know which transport was used.
 */
export function upload<T>(
  path: string,
  form: FormData,
  opts: { onProgress?: (fraction: number) => void; signal?: AbortSignal } = {},
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE}/api${path}`, true);
    xhr.withCredentials = true;
    xhr.setRequestHeader('Accept', 'application/json');

    if (opts.onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) opts.onProgress!(e.loaded / e.total);
      };
    }

    const fail = (status: number, message: string) =>
      reject(new HttpError(status, { code: 'unknown', message }));

    xhr.onload = () => {
      let payload: unknown;
      try { payload = JSON.parse(xhr.responseText); } catch { payload = null; }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve((payload ?? undefined) as T);
      } else {
        const api = (payload ?? {}) as Partial<ApiError> & { detail?: string };
        // FastAPI puts the message on `detail`; keep both shapes working.
        fail(xhr.status, api.message ?? api.detail ?? xhr.statusText);
      }
    };
    xhr.onerror = () => fail(0, 'The upload could not reach IRIS.');
    xhr.ontimeout = () => fail(0, 'The upload timed out.');
    xhr.onabort = () => fail(0, 'Upload cancelled.');

    opts.signal?.addEventListener('abort', () => xhr.abort(), { once: true });
    xhr.send(form);
  });
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

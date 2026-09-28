/**
 * API client — wraps fetch with JSON handling and one error shape.
 * Per-domain calls (chat, habits, etc.) sit on top.
 */

import type { ApiError } from '@/types/api';
import { tracedRequest } from '@/lib/telemetry';
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

/**
 * One shape for every failure, whatever the transport.
 *
 * FastAPI puts its message on `detail` — a string, or a list of validation
 * errors — while ApiError expects `message`. request() read only `message`, so
 * every server-side refusal reached the screen with no text at all; upload()
 * already handled both. All three transports use this now.
 */
function toApiError(status: number, payload: unknown, fallback: string): ApiError {
  const p = (payload ?? {}) as Partial<ApiError> & { detail?: unknown };
  const detail = Array.isArray(p.detail)
    ? (p.detail[0] as { msg?: string } | undefined)?.msg
    : typeof p.detail === 'string' ? p.detail : undefined;
  return { code: p.code ?? `http_${status}`, message: p.message ?? detail ?? fallback };
}

async function request<T>(
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<T> {
  const traced = tracedRequest(method, path);
  let res: Response;
  try {
    res = await fetch(`${BASE}/api${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        ...traced.headers,
      },
      credentials: 'include',
      body: body == null ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    traced.finish(0, String(err));
    throw err;
  }
  traced.finish(res.status);

  if (!res.ok) {
    let payload: unknown = null;
    try { payload = await res.json(); } catch { /* not JSON: fall back below */ }
    throw new HttpError(res.status, toApiError(res.status, payload, res.statusText));
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
    const traced = tracedRequest('POST', path);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE}/api${path}`, true);
    xhr.withCredentials = true;
    xhr.setRequestHeader('Accept', 'application/json');
    for (const [key, value] of Object.entries(traced.headers)) xhr.setRequestHeader(key, value);

    if (opts.onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) opts.onProgress!(e.loaded / e.total);
      };
    }

    const fail = (status: number, message: string) =>
      reject(new HttpError(status, { code: 'unknown', message }));

    xhr.onload = () => {
      traced.finish(xhr.status);
      let payload: unknown;
      try { payload = JSON.parse(xhr.responseText); } catch { payload = null; }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve((payload ?? undefined) as T);
      } else {
        reject(new HttpError(xhr.status, toApiError(xhr.status, payload, xhr.statusText)));
      }
    };
    xhr.onerror = () => { traced.finish(0, 'The upload could not reach IRIS.'); fail(0, 'The upload could not reach IRIS.'); };
    xhr.ontimeout = () => { traced.finish(0, 'The upload timed out.'); fail(0, 'The upload timed out.'); };
    xhr.onabort = () => { traced.finish(0, 'Upload cancelled.'); fail(0, 'Upload cancelled.'); };

    opts.signal?.addEventListener('abort', () => xhr.abort(), { once: true });
    xhr.send(form);
  });
}

export const api = {
  get:    <T>(path: string)                 => request<T>('GET',    path),
  post:   <T>(path: string, body?: unknown) => request<T>('POST',   path, body),
  patch:  <T>(path: string, body?: unknown) => request<T>('PATCH',  path, body),
  put:    <T>(path: string, body?: unknown) => request<T>('PUT',    path, body),
  del:    <T>(path: string)                 => request<T>('DELETE', path),
};

/**
 * Stream Server-Sent Events from a path (used for IRIS's chat replies).
 * Yields each `data:` payload as it arrives. Caller is responsible for breaking.
 */
export async function* sse<T = unknown>(path: string, body: unknown): AsyncGenerator<T> {
  const traced = tracedRequest('POST', path);
  const started = performance.now();
  let res: Response;
  try {
    res = await fetch(`${BASE}/api${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...traced.headers },
      credentials: 'include',
      body: JSON.stringify(body),
    });
  } catch (err) {
    traced.finish(0, String(err));
    throw err;
  }
  if (!res.ok || !res.body) {
    traced.finish(res.status);
    let payload: unknown = null;
    try { payload = await res.json(); } catch { /* not JSON */ }
    throw new HttpError(res.status, toApiError(res.status, payload, 'IRIS could not be reached.'));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let ttfb: number | undefined;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (ttfb == null && value) ttfb = performance.now() - started;
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
  } finally {
    traced.finish(res.status, undefined, ttfb == null ? undefined : { 'iris.client.ttfb_ms': ttfb });
  }
}

/**
 * A raw POST for bodies request() does not send (form data) or answers it does
 * not parse (audio), with the same URL base and the same error shape.
 */
export async function postRaw(path: string, init: RequestInit, fallback: string): Promise<Response> {
  const traced = tracedRequest('POST', path);
  const headers = new Headers(init.headers);
  for (const [key, value] of Object.entries(traced.headers)) headers.set(key, value);
  let res: Response;
  try {
    res = await fetch(`${BASE}/api${path}`, { method: 'POST', credentials: 'include', ...init, headers });
  } catch (err) {
    traced.finish(0, String(err));
    throw err;
  }
  traced.finish(res.status);
  if (!res.ok) {
    let payload: unknown = null;
    try { payload = await res.json(); } catch { /* not JSON */ }
    throw new HttpError(res.status, toApiError(res.status, payload, fallback));
  }
  return res;
}

export { HttpError };

/**
 * Import API — bringing existing writing in from other tools.
 *   GET    /api/import/adapters                   → ImportAdapter[]
 *   POST   /api/import/batches      (multipart)   → ImportBatch
 *   GET    /api/import/batches                    → ImportBatch[]
 *   GET    /api/import/batches/:id                → ImportBatch
 *   GET    /api/import/batches/:id/entries        → { entries }
 *   PATCH  /api/import/entries/:id                → ImportEntry
 *   POST   /api/import/entries/bulk               → { updated }
 *   POST   /api/import/batches/:id/reparse        → ImportBatch
 *   POST   /api/import/batches/:id/commit         → CommitResult
 *   DELETE /api/import/batches/:id                → { deleted }
 *   POST   /api/import/audio        (multipart)   → staged recording
 *
 * Named `importing.ts`, not `import.ts`: the latter reads as the keyword at
 * every call site.
 */

import { api, upload } from './client';
import type {
  CommitResult, ImportAdapter, ImportBatch, ImportEntry,
} from '@/types/api';

export async function listAdapters(): Promise<ImportAdapter[]> {
  return api.get('/import/adapters');
}

export async function uploadExport(
  file: File,
  opts: { adapter?: string; onProgress?: (fraction: number) => void; signal?: AbortSignal } = {},
): Promise<ImportBatch> {
  const form = new FormData();
  form.append('file', file);
  if (opts.adapter) form.append('adapter', opts.adapter);
  return upload('/import/batches', form, opts);
}

export async function uploadRecording(
  file: File | Blob,
  opts: {
    filename?: string;
    recordedAt?: string;
    capturedSource?: 'upload' | 'recording';
    batchId?: string;
    onProgress?: (fraction: number) => void;
  } = {},
): Promise<{ batchId: string; entryId: string; durationSeconds: number | null }> {
  const form = new FormData();
  form.append('file', file, opts.filename ?? 'recording.webm');
  if (opts.recordedAt) form.append('recordedAt', opts.recordedAt);
  form.append('capturedSource', opts.capturedSource ?? 'upload');
  if (opts.batchId) form.append('batchId', opts.batchId);
  return upload('/import/audio', form, { onProgress: opts.onProgress });
}

export async function listBatches(): Promise<ImportBatch[]> {
  return api.get('/import/batches');
}

export async function getBatch(id: string): Promise<ImportBatch> {
  return api.get(`/import/batches/${id}`);
}

export async function listEntries(id: string): Promise<ImportEntry[]> {
  const body = await api.get<{ entries: ImportEntry[] }>(`/import/batches/${id}/entries`);
  return body.entries;
}

export async function updateEntry(
  entryId: string,
  patch: { occurredOn?: string; status?: 'staged' | 'excluded'; content?: string },
): Promise<ImportEntry> {
  return api.patch(`/import/entries/${entryId}`, patch);
}

export async function bulkUpdate(
  ids: string[],
  op: 'exclude' | 'include' | 'set_date',
  occurredOn?: string,
): Promise<{ updated: number }> {
  return api.post('/import/entries/bulk', { ids: ids.map(Number), op, occurredOn });
}

export async function reparse(id: string, adapter: string): Promise<ImportBatch> {
  return api.post(`/import/batches/${id}/reparse`, { adapter });
}

export async function commit(id: string): Promise<CommitResult> {
  return api.post(`/import/batches/${id}/commit`);
}

export async function discard(id: string, withReflections = false): Promise<void> {
  await api.del(`/import/batches/${id}?withReflections=${withReflections}`);
}

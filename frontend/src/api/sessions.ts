/**
 * Therapy sessions (ADR-0028) — a transcript waits here until the owner imports it.
 *   GET    /api/sessions/imports                 → { imports }
 *   POST   /api/sessions/imports     (multipart) → SessionImport   (staged; nothing sent)
 *   GET    /api/sessions/imports/:id             → SessionImport
 *   PATCH  /api/sessions/imports/:id             → SessionImport   (day and time, language, who is who)
 *   POST   /api/sessions/imports/:id/commit      → SessionImport   (the owner's click)
 *   POST   /api/sessions/imports/:id/undo        → SessionImport   (out of the journal, back to waiting)
 *   DELETE /api/sessions/imports/:id             → SessionImport   (discarded)
 *   POST   /api/sessions/imports/:id/recording  (multipart) → SessionImport  (kept here; nothing sent)
 *   POST   /api/sessions/imports/:id/voices     → SessionImport   (the click that sends the recording)
 *   POST   /api/sessions/imports/:id/voices/undo → SessionImport  (the transcript's own labels back)
 */

import { api, upload } from './client';
import type { SessionImport } from '@/types/api';

export interface SessionImportChanges {
  startedAt?: string;
  language?: string;
  owner?: string | null;
  therapist?: string | null;
}

export async function listSessionImports(): Promise<SessionImport[]> {
  return (await api.get<{ imports: SessionImport[] }>('/sessions/imports')).imports;
}

export async function uploadSessionTranscript(
  file: File, opts: { onProgress?: (fraction: number) => void } = {},
): Promise<SessionImport> {
  const form = new FormData();
  form.append('file', file);
  return upload('/sessions/imports', form, opts);
}

export const updateSessionImport = (id: string, changes: SessionImportChanges) =>
  api.patch<SessionImport>(`/sessions/imports/${id}`, changes);

export const commitSessionImport = (id: string) =>
  api.post<SessionImport>(`/sessions/imports/${id}/commit`);

export const undoSessionImport = (id: string) =>
  api.post<SessionImport>(`/sessions/imports/${id}/undo`);

export const discardSessionImport = (id: string) =>
  api.del<SessionImport>(`/sessions/imports/${id}`);

export async function uploadSessionRecording(
  id: string, file: File, opts: { onProgress?: (fraction: number) => void } = {},
): Promise<SessionImport> {
  const form = new FormData();
  form.append('file', file);
  return upload(`/sessions/imports/${id}/recording`, form, opts);
}

export const startSessionVoices = (id: string) =>
  api.post<SessionImport>(`/sessions/imports/${id}/voices`);

export const undoSessionVoices = (id: string) =>
  api.post<SessionImport>(`/sessions/imports/${id}/voices/undo`);

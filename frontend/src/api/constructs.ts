/**
 * Constructs API — patterns IRIS noticed by reading, awaiting your decision.
 *   GET  /api/constructs?status=candidate  → { constructs }
 *   POST /api/constructs/discover          → { constructs }
 *   GET  /api/constructs/last-run          → { run }  (counts only)
 *   POST /api/constructs/:id/confirm       → { id, status, occurrences }
 *   POST /api/constructs/:id/reject        → { id, status }
 *
 * Discovery is the only path that sends the whole archive to the model, and it
 * happens when the owner presses the button and at no other time.
 */

import { api } from './client';
import type { ConstructCandidate, DiscoveryRun } from '@/types/api';

export async function listCandidates(): Promise<ConstructCandidate[]> {
  const body = await api.get<{ constructs: ConstructCandidate[] }>('/constructs?status=candidate');
  return body.constructs;
}

export async function discoverConstructs(includeStaged = true): Promise<ConstructCandidate[]> {
  const body = await api.post<{ constructs: ConstructCandidate[] }>(
    '/constructs/discover', { includeStaged });
  return body.constructs;
}

export async function confirmConstruct(id: string): Promise<{ occurrences: number }> {
  return api.post(`/constructs/${id}/confirm`, {});
}

export async function rejectConstruct(id: string): Promise<{ status: string }> {
  return api.post(`/constructs/${id}/reject`, {});
}

export async function getLastRun(): Promise<DiscoveryRun | null> {
  const body = await api.get<{ run: DiscoveryRun | null }>('/constructs/last-run');
  return body.run;
}

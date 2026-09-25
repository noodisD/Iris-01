/**
 * Settings API — WIRED LIVE (single-user backend).
 *   GET    /api/user                        → User
 *   PATCH  /api/user/preferences            → User
 *   GET    /api/knowledge                   → KnownFact[]   (mapped from themes)
 *   DELETE /api/knowledge/:id               → forget a fact (a cluster is deleted,
 *                                             a confirmed pattern is retracted)
 *   GET    /api/user/analysis               → AnalysisPreferences
 *   PATCH  /api/user/analysis               → AnalysisPreferences
 *   POST   /api/user/analysis/reset         → AnalysisPreferences
 */

import { api } from './client';
import type { User, UserPreferences, AnalysisPreferences, KnownFact } from '@/types/api';

export async function getUser(): Promise<User> {
  return api.get('/user');
}

export async function updatePreferences(prefs: Partial<UserPreferences>): Promise<User> {
  return api.patch('/user/preferences', prefs);
}

export async function getKnownFacts(): Promise<KnownFact[]> {
  return api.get('/knowledge');
}

export async function forgetFact(id: string): Promise<void> {
  await api.del(`/knowledge/${id}`);
}

export async function getAnalysisPreferences(): Promise<AnalysisPreferences> {
  return api.get('/user/analysis');
}

export async function updateAnalysisPreferences(
  prefs: Partial<Omit<AnalysisPreferences, 'availableEngines'>>,
): Promise<AnalysisPreferences> {
  return api.patch('/user/analysis', prefs);
}

export async function resetAnalysisPreferences(): Promise<AnalysisPreferences> {
  return api.post('/user/analysis/reset');
}

export interface MobileConnection {
  lan_url: string | null;
  public_key_sha256: string | null;
  listener: 'listening' | 'failed' | 'not_started' | 'not_configured';
  listener_error: string | null;
  paired: boolean;
  paired_at: string | null;
  last_seen_at: string | null;
  last_intake_at: string | null;
  last_rejection: { at: string; status: number; detail: string } | null;
  pending_batches: number;
}

export function phonePairingCode(url: string, key: string, token?: string): string {
  return JSON.stringify(token ? { iris: 1, url, key, token } : { iris: 1, url, key });
}

export async function getMobileConnection(): Promise<MobileConnection> {
  return api.get('/mobile/connection');
}

export async function pairMobile(token: string): Promise<void> {
  await api.post('/mobile/pair', { token, lan_bind_enabled: true });
}

export async function unpairMobile(): Promise<void> {
  await api.post('/mobile/unpair');
}

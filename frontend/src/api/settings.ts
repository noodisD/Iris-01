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

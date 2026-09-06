/**
 * Settings API — WIRED LIVE (single-user backend).
 *   GET    /api/user                        → User
 *   PATCH  /api/user/preferences            → User
 *   GET    /api/knowledge                   → KnownFact[]   (mapped from themes)
 *   DELETE /api/knowledge/:id               → forget a fact (deletes the theme)
 *   GET    /api/connectors                  → DataConnector[]   (static catalog)
 *   POST   /api/connectors/:id/:action      → DataConnector     (connect|pause|disconnect)
 */

import { api } from './client';
import type { User, UserPreferences, KnownFact, DataConnector } from '@/types/api';

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

export async function getConnectors(): Promise<DataConnector[]> {
  return api.get('/connectors');
}

export async function setConnectorState(id: string, action: 'connect' | 'pause' | 'disconnect'): Promise<DataConnector> {
  return api.post(`/connectors/${id}/${action}`);
}

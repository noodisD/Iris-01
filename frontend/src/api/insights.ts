/**
 * Insights API — WIRED LIVE (single-user backend; built from the analytical engines).
 *   GET    /api/insights                     → InsightSummary[]
 *   GET    /api/insights/:id                 → InsightDetail
 *   POST   /api/insights/:id/snooze          → InsightSummary (status: snoozed)
 *   POST   /api/insights/:id/resolve         → InsightSummary (status: resolved)
 *   POST   /api/insights/:id/suggestions/:sid/accept → 204
 */

import { api } from './client';
import type { InsightDetail, InsightSummary } from '@/types/api';

export async function listInsights(): Promise<InsightSummary[]> {
  return api.get('/insights');
}

export async function getInsight(id: string): Promise<InsightDetail | null> {
  return api.get(`/insights/${id}`);
}

export async function snoozeInsight(id: string, days = 30): Promise<InsightSummary> {
  return api.post(`/insights/${id}/snooze`, { days });
}

export async function resolveInsight(id: string): Promise<InsightSummary> {
  return api.post(`/insights/${id}/resolve`);
}

export async function acceptSuggestion(insightId: string, suggestionId: string): Promise<void> {
  await api.post(`/insights/${insightId}/suggestions/${suggestionId}/accept`);
}

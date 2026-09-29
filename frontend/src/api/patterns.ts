/**
 * Patterns API — discovery: library patterns and the occasions that are instances of them.
 *
 * Backend endpoints (iris_api.py):
 *   GET /api/patterns                          → { patterns: PatternSummary[] }
 *   GET /api/patterns/:id                      → PatternDetail
 *   PUT /api/patterns/:id/occasions/:occasion  → { ok }   is this occasion an instance?
 *   PUT /api/patterns/:id/verdict              → { ok }   does the pattern ring true?
 *   GET /api/differences                       → { differences: Difference[] }   the Insights screen
 *   PUT /api/differences/:id/:other/verdict    → { ok }   does this difference ring true?
 */

import { api } from './client';
import type {
  Coverage, Difference, DifferenceDetail, DiscoveryRange, DiscoveryStatus, OccasionFeedback,
  OutcomePair, PatternDetail, PatternSummary, PatternVerdict,
} from '@/types/api';

export async function getPatterns(period: DiscoveryRange = 'all'): Promise<{ patterns: PatternSummary[]; coverage: Coverage }> {
  return api.get(`/patterns?range=${period}`);
}

export async function getPattern(id: string, period: DiscoveryRange = 'all'): Promise<PatternDetail> {
  return api.get(`/patterns/${encodeURIComponent(id)}?range=${period}`);
}

export async function setOccasionVerdict(patternId: string, occasionId: string,
                                         feedback: OccasionFeedback): Promise<{ ok: boolean }> {
  return api.put(`/patterns/${encodeURIComponent(patternId)}/occasions/${encodeURIComponent(occasionId)}`, feedback);
}

export async function setPatternVerdict(patternId: string, feedback: PatternVerdict): Promise<{ ok: boolean }> {
  return api.put(`/patterns/${encodeURIComponent(patternId)}/verdict`, feedback);
}

export async function getDifferences(period: DiscoveryRange = 'all'): Promise<{
  differences: Difference[]; reflections: OutcomePair[]; coverage: Coverage; snapshot: string;
}> {
  return api.get(`/differences?range=${period}`);
}

export function getDifferenceDetail(patternId: string, otherId: string, period: DiscoveryRange): Promise<DifferenceDetail> {
  return api.get(`/differences/${encodeURIComponent(patternId)}/${encodeURIComponent(otherId)}?range=${period}`);
}

export async function setDifferenceVerdict(patternId: string, otherId: string,
                                           feedback: PatternVerdict): Promise<{ ok: boolean }> {
  return api.put(`/differences/${encodeURIComponent(patternId)}/${encodeURIComponent(otherId)}/verdict`, feedback);
}

export function getDiscoveryStatus(): Promise<DiscoveryStatus> {
  return api.get('/discovery/status');
}

export function refreshDiscovery(scope: 'unread' | 'failed'): Promise<{ queuedEntries: number }> {
  return api.post('/discovery/refresh', { scope });
}

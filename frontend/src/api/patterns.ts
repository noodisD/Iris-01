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
import type { Difference, OccasionVerdictValue, PatternDetail, PatternSummary, PatternVerdictValue } from '@/types/api';

export async function getPatterns(): Promise<{ patterns: PatternSummary[] }> {
  return api.get('/patterns');
}

export async function getPattern(id: string): Promise<PatternDetail> {
  return api.get(`/patterns/${id}`);
}

export async function setOccasionVerdict(patternId: string, occasionId: string,
                                         verdict: OccasionVerdictValue | null): Promise<{ ok: boolean }> {
  return api.put(`/patterns/${patternId}/occasions/${occasionId}`, { verdict });
}

export async function setPatternVerdict(patternId: string, verdict: PatternVerdictValue): Promise<{ ok: boolean }> {
  return api.put(`/patterns/${patternId}/verdict`, { verdict });
}

export async function getDifferences(): Promise<{ differences: Difference[] }> {
  return api.get('/differences');
}

export async function setDifferenceVerdict(patternId: string, otherId: string,
                                           verdict: PatternVerdictValue): Promise<{ ok: boolean }> {
  return api.put(`/differences/${patternId}/${otherId}/verdict`, { verdict });
}

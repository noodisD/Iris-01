/**
 * Review API — WIRED LIVE (single-user backend; weekly aggregation + LLM letter).
 *   GET /api/review/latest               → ReviewWeek
 *   GET /api/review/week/:isoWeekStart   → ReviewWeek
 */

import { api } from './client';
import type { ReviewWeek } from '@/types/api';

export async function getLatestWeek(): Promise<ReviewWeek> {
  return api.get('/review/latest');
}

export async function getWeek(start: string): Promise<ReviewWeek> {
  return api.get(`/review/week/${start}`);
}

/**
 * Review API — WIRED LIVE (single-user backend; weekly aggregation + LLM letter).
 *   GET /api/review/latest               → ReviewWeek
 */

import { api } from './client';
import type { ReviewWeek } from '@/types/api';

export async function getLatestWeek(): Promise<ReviewWeek> {
  return api.get('/review/latest');
}

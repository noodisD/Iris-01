/**
 * Body / wearable signals
 *   GET /api/body/overview        → BodyOverviewResponse  (14-day window)
 *   GET /api/body/day/:date       → BodyDay
 *   GET /api/body/source          → BodySource
 */

import { api, useMocks } from './client';
import type { BodyDay, BodyOverviewResponse, BodySource } from '@/types/api';
import { mockBody } from '@/lib/mock';

const delay = (ms: number) => new Promise(r => setTimeout(r, ms));

export async function getBodyOverview(): Promise<BodyOverviewResponse> {
  if (useMocks()) { await delay(120); return mockBody; }
  return api.get('/body/overview');
}

export async function getBodyDay(date: string): Promise<BodyDay | null> {
  if (useMocks()) {
    await delay(80);
    return mockBody.recent.find(d => d.date === date) ?? null;
  }
  return api.get(`/body/day/${date}`);
}

export async function getBodySource(): Promise<BodySource> {
  if (useMocks()) { await delay(60); return mockBody.source; }
  return api.get('/body/source');
}

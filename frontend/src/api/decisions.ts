/**
 * Decisions API — a log of risky commitments, recorded when one is made.
 *
 * Backend endpoints (iris_api.py):
 *   GET   /api/decisions        → { decisions: Decision[] }   newest first
 *   POST  /api/decisions        → Decision                    (only `what` required)
 *   PATCH /api/decisions/:id    → Decision                    (the outcome, later)
 */

import { api } from './client';
import type { Decision, DecisionCreate, DecisionOutcome } from '@/types/api';

export async function getDecisions(): Promise<{ decisions: Decision[] }> {
  return api.get('/decisions');
}

export async function createDecision(input: DecisionCreate): Promise<Decision> {
  return api.post('/decisions', input);
}

export async function recordOutcome(id: string, input: DecisionOutcome): Promise<Decision> {
  return api.patch(`/decisions/${id}`, input);
}

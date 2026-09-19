/**
 * Onboarding API (single-user backend).
 *   GET  /api/onboarding/state     → OnboardingState ('welcome' until first run, then 'done')
 *   POST /api/onboarding/complete  → User
 */

import { api } from './client';
import type { OnboardingState, User } from '@/types/api';

export async function getOnboarding(): Promise<OnboardingState> {
  return api.get('/onboarding/state');
}

export async function completeOnboarding(): Promise<User> {
  return api.post('/onboarding/complete');
}

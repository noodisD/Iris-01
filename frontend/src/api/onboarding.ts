/**
 * Onboarding API — WIRED LIVE (single-user backend; configures the local user).
 *   GET  /api/onboarding/state            → OnboardingState
 *   POST /api/onboarding/answer           → OnboardingState  (body: { step, answer })
 *   POST /api/onboarding/complete         → User
 */

import { api } from './client';
import type { OnboardingState, User } from '@/types/api';

export async function getOnboarding(): Promise<OnboardingState> {
  return api.get('/onboarding/state');
}

export async function answerOnboarding(step: OnboardingState['step'], answer: unknown): Promise<OnboardingState> {
  return api.post('/onboarding/answer', { step, answer });
}

export async function completeOnboarding(): Promise<User> {
  return api.post('/onboarding/complete');
}

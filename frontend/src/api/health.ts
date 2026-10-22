import { api } from './client';
import type { HealthLatest } from '@/types/api';

/** The doctor's last stored run: what was not fine, and when it was checked. */
export function getHealthLatest(): Promise<HealthLatest> {
  return api.get<HealthLatest>('/health/latest');
}

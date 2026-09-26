import { api } from './client';
import type { DayDifference, PatternVerdictValue } from '@/types/api';

export function getDayDifferences(): Promise<{ differences: DayDifference[] }> {
  return api.get('/day-differences');
}

export function setDayDifferenceVerdict(outcome: DayDifference['outcome'], split: DayDifference['split'],
                                        verdict: PatternVerdictValue): Promise<{ ok: boolean }> {
  return api.put(`/day-differences/${encodeURIComponent(outcome)}/${encodeURIComponent(split)}/verdict`, { verdict });
}

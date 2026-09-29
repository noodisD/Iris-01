import { api } from './client';
import type { DayDiagnostics, DayDifference, DayDifferenceDetail, DiscoveryRange, PatternVerdict } from '@/types/api';

export function getDayDifferences(period: DiscoveryRange = 'all'): Promise<{
  differences: DayDifference[]; diagnostics: DayDiagnostics;
}> {
  return api.get(`/day-differences?range=${period}`);
}

export function getDayDifferenceDetail(outcome: DayDifference['outcome'], split: DayDifference['split'],
                                       period: DiscoveryRange): Promise<DayDifferenceDetail> {
  return api.get(`/day-differences/${encodeURIComponent(outcome)}/${encodeURIComponent(split)}?range=${period}`);
}

export function setDayDifferenceVerdict(outcome: DayDifference['outcome'], split: DayDifference['split'],
                                        feedback: PatternVerdict): Promise<{ ok: boolean }> {
  return api.put(`/day-differences/${encodeURIComponent(outcome)}/${encodeURIComponent(split)}/verdict`, feedback);
}

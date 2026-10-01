import { api } from './client';
import type {
  AccountVerdictValue, Coverage, DiscoveryRange, DiscoveryStatus, FeedbackRequest,
  InsightDetail, PatternDetail, PatternVerdictValue, PersonalInsight, PersonalPattern,
  SavedFeedback,
} from '@/types/api';

export function getPatterns(period: DiscoveryRange = 'all'): Promise<{
  patterns: PersonalPattern[]; coverage: Coverage; status: DiscoveryStatus; snapshot: string;
}> {
  return api.get(`/patterns?range=${period}`);
}

export function getPattern(id: string, period: DiscoveryRange = 'all'): Promise<PatternDetail> {
  return api.get(`/patterns/${encodeURIComponent(id)}?range=${period}`);
}

export function getPersonalInsights(period: DiscoveryRange = 'all'): Promise<{
  insights: PersonalInsight[]; coverage: Coverage; status: DiscoveryStatus; snapshot: string;
}> {
  return api.get(`/personal-insights?range=${period}`);
}

export function getPersonalInsight(id: string, period: DiscoveryRange = 'all'): Promise<InsightDetail> {
  return api.get(`/personal-insights/${encodeURIComponent(id)}?range=${period}`);
}

export function setAccountVerdict(dynamicId: string, accountId: string,
  feedback: FeedbackRequest<AccountVerdictValue>): Promise<{ ok: true }> {
  return api.put(`/patterns/${encodeURIComponent(dynamicId)}/accounts/${encodeURIComponent(accountId)}`, feedback);
}

export function setPatternVerdict(id: string, feedback: FeedbackRequest<PatternVerdictValue>): Promise<{
  feedback: SavedFeedback<PatternVerdictValue> | null; snapshot: string;
}> {
  return api.put(`/patterns/${encodeURIComponent(id)}/verdict`, feedback);
}

export function setInsightVerdict(id: string, feedback: FeedbackRequest<PatternVerdictValue>): Promise<{
  feedback: SavedFeedback<PatternVerdictValue> | null; snapshot: string;
}> {
  return api.put(`/personal-insights/${encodeURIComponent(id)}/verdict`, feedback);
}

export function getDiscoveryStatus(): Promise<DiscoveryStatus> {
  return api.get('/discovery/status');
}

export function refreshDiscovery(scope: 'unread' | 'failed'): Promise<{
  queuedEntries: number; queuedSynthesis: boolean;
}> {
  return api.post('/discovery/refresh', { scope });
}

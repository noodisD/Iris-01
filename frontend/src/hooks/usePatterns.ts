import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import * as patternsApi from '@/api/patterns';
import * as dayDifferencesApi from '@/api/dayDifferences';
import type { AccountVerdictValue, DayDifference, DiscoveryRange, DiscoveryStatus,
  FeedbackRequest, PatternVerdict, PatternVerdictValue } from '@/types/api';

export function usePatterns(period: DiscoveryRange = 'all') {
  return useQuery({ queryKey: qk.summaries(period), queryFn: () => patternsApi.getPatterns(period) });
}

export function usePattern(id: string | undefined, period: DiscoveryRange = 'all') {
  return useQuery({ queryKey: qk.pattern(id ?? '', period),
    queryFn: () => patternsApi.getPattern(id!, period), enabled: Boolean(id) });
}

export function usePersonalInsights(period: DiscoveryRange = 'all') {
  return useQuery({ queryKey: qk.insights(period), queryFn: () => patternsApi.getPersonalInsights(period) });
}

export function usePersonalInsight(id: string, period: DiscoveryRange, enabled: boolean) {
  return useQuery({ queryKey: qk.insight(id, period),
    queryFn: () => patternsApi.getPersonalInsight(id, period), enabled });
}

function useRefreshing<V>(fn: (v: V) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn,
    onSuccess: () => { qc.invalidateQueries({ queryKey: qk.patterns }); },
  });
}

export function useAccountVerdict(dynamicId: string) {
  return useRefreshing(({ accountId, feedback }: { accountId: string;
    feedback: FeedbackRequest<AccountVerdictValue> }) =>
    patternsApi.setAccountVerdict(dynamicId, accountId, feedback));
}

export function usePatternVerdict(dynamicId: string) {
  return useRefreshing((feedback: FeedbackRequest<PatternVerdictValue>) =>
    patternsApi.setPatternVerdict(dynamicId, feedback));
}

export function useInsightVerdict(insightId: string) {
  return useRefreshing((feedback: FeedbackRequest<PatternVerdictValue>) =>
    patternsApi.setInsightVerdict(insightId, feedback));
}

/** Measured-day comparisons load independently from writing-derived Insights. */
export function useDayDifferences(period: DiscoveryRange = 'all') {
  return useQuery({ queryKey: qk.dayDifferences(period), queryFn: () => dayDifferencesApi.getDayDifferences(period) });
}
export function useDayDifferenceDetail(outcome: DayDifference['outcome'], split: DayDifference['split'],
                                       period: DiscoveryRange, snapshot: string, enabled: boolean) {
  return useQuery({ queryKey: qk.dayDifferenceDetail(outcome, split, period, snapshot),
    queryFn: () => dayDifferencesApi.getDayDifferenceDetail(outcome, split, period), enabled });
}

export function useDayDifferenceVerdict() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: ({ outcome, split, feedback }: {
    outcome: DayDifference['outcome']; split: DayDifference['split']; feedback: PatternVerdict;
  }) => dayDifferencesApi.setDayDifferenceVerdict(outcome, split, feedback),
  onSuccess: () => { qc.invalidateQueries({ queryKey: qk.dayDifferencesRoot }); } });
}

/** Poll only while visible and reading or synthesis is in progress. */
export function useDiscoveryStatus() {
  const [visible, setVisible] = useState(() => document.visibilityState === 'visible');
  const qc = useQueryClient();
  const previous = useRef<DiscoveryStatus | null>(null);
  useEffect(() => {
    const onVisibility = () => {
      const showing = document.visibilityState === 'visible';
      setVisible(showing);
      if (showing) qc.invalidateQueries({ queryKey: qk.discoveryStatus });
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [qc]);
  const query = useQuery({ queryKey: qk.discoveryStatus, queryFn: patternsApi.getDiscoveryStatus,
    enabled: visible,
    refetchInterval: query => visible && (query.state.data?.pendingEntries || query.state.data?.synthesisPending)
      ? 5000 : false,
  });
  useEffect(() => {
    if (!query.data) return;
    const prior = previous.current;
    previous.current = query.data;
    if (prior && (prior.currentEntries !== query.data.currentEntries
      || prior.lastCompletedAt !== query.data.lastCompletedAt || prior.stage !== query.data.stage)) {
      qc.invalidateQueries({ predicate: q => q.queryKey[0] === 'patterns' && q.queryKey[1] !== 'status' });
    }
  }, [query.data, qc]);
  return query;
}

export function useDiscoveryRefresh() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: patternsApi.refreshDiscovery,
    onSuccess: () => { qc.invalidateQueries({ queryKey: qk.discoveryStatus }); } });
}

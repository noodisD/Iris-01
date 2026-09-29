import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import * as patternsApi from '@/api/patterns';
import * as dayDifferencesApi from '@/api/dayDifferences';
import type { DayDifference, DiscoveryRange, DiscoveryStatus, OccasionFeedback, PatternVerdict } from '@/types/api';

export function usePatterns(period: DiscoveryRange = 'all') {
  return useQuery({ queryKey: qk.summaries(period), queryFn: () => patternsApi.getPatterns(period) });
}

export function usePattern(id: string | undefined, period: DiscoveryRange = 'all') {
  return useQuery({
    queryKey: qk.pattern(id ?? '', period),
    queryFn: () => patternsApi.getPattern(id!, period),
    enabled: Boolean(id),
  });
}

/** Account corrections change every writing view, including comparisons. */
function useRefreshing<V>(fn: (v: V) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => { qc.invalidateQueries({ queryKey: qk.patterns }); },
  });
}

export function useOccasionVerdict(patternId: string) {
  return useRefreshing(({ occasionId, feedback }: { occasionId: string; feedback: OccasionFeedback }) =>
    patternsApi.setOccasionVerdict(patternId, occasionId, feedback));
}

export function usePatternVerdict(patternId: string) {
  return useRefreshing((feedback: PatternVerdict) => patternsApi.setPatternVerdict(patternId, feedback));
}

export function useDifferences(period: DiscoveryRange = 'all') {
  return useQuery({ queryKey: qk.differences(period), queryFn: () => patternsApi.getDifferences(period) });
}
export function useDifferenceDetail(patternId: string, otherId: string, period: DiscoveryRange,
                                    snapshot: string, enabled: boolean) {
  return useQuery({
    queryKey: qk.differenceDetail(patternId, otherId, period, snapshot),
    queryFn: () => patternsApi.getDifferenceDetail(patternId, otherId, period),
    enabled,
  });
}


export function useDifferenceVerdict() {
  return useRefreshing(({ patternId, otherId, feedback }: {
    patternId: string; otherId: string; feedback: PatternVerdict;
  }) => patternsApi.setDifferenceVerdict(patternId, otherId, feedback));
}

/** Measured-day comparisons load independently from writing-derived Insights. */
export function useDayDifferences(period: DiscoveryRange = 'all') {
  return useQuery({ queryKey: qk.dayDifferences(period), queryFn: () => dayDifferencesApi.getDayDifferences(period) });
}
export function useDayDifferenceDetail(outcome: DayDifference['outcome'], split: DayDifference['split'],
                                       period: DiscoveryRange, snapshot: string, enabled: boolean) {
  return useQuery({
    queryKey: qk.dayDifferenceDetail(outcome, split, period, snapshot),
    queryFn: () => dayDifferencesApi.getDayDifferenceDetail(outcome, split, period),
    enabled,
  });
}


export function useDayDifferenceVerdict() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ outcome, split, feedback }: {
      outcome: DayDifference['outcome']; split: DayDifference['split']; feedback: PatternVerdict;
    }) => dayDifferencesApi.setDayDifferenceVerdict(outcome, split, feedback),
    onSuccess: () => { qc.invalidateQueries({ queryKey: qk.dayDifferencesRoot }); },
  });
}

/** A mounted discovery page polls only while visible and work is pending. */
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

  const query = useQuery({
    queryKey: qk.discoveryStatus,
    queryFn: patternsApi.getDiscoveryStatus,
    enabled: visible,
    refetchInterval: query => visible && (query.state.data?.pendingEntries ?? 0) > 0 ? 5000 : false,
  });
  useEffect(() => {
    if (!query.data) return;
    const prior = previous.current;
    previous.current = query.data;
    if (prior && (prior.currentEntries !== query.data.currentEntries
      || prior.lastCompletedAt !== query.data.lastCompletedAt)) {
      qc.invalidateQueries({ predicate: q => q.queryKey[0] === 'patterns' && q.queryKey[1] !== 'status' });
    }
  }, [query.data, qc]);
  return query;
}

export function useDiscoveryRefresh() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: patternsApi.refreshDiscovery,
    onSuccess: () => { qc.invalidateQueries({ queryKey: qk.discoveryStatus }); },
  });
}

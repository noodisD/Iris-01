import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import * as patternsApi from '@/api/patterns';
import type { OccasionVerdictValue, PatternVerdictValue } from '@/types/api';

export function usePatterns() {
  return useQuery({ queryKey: qk.patterns, queryFn: patternsApi.getPatterns });
}

export function usePattern(id: string | undefined) {
  return useQuery({
    queryKey: qk.pattern(id ?? ''),
    queryFn: () => patternsApi.getPattern(id!),
    enabled: Boolean(id),
  });
}

/** A verdict changes the counts on the list as well as the detail, so both refetch. */
function useRefreshing<V>(fn: (v: V) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSettled: () => { qc.invalidateQueries({ queryKey: qk.patterns }); },
  });
}

export function useOccasionVerdict(patternId: string) {
  return useRefreshing(({ occasionId, verdict }: { occasionId: string; verdict: OccasionVerdictValue | null }) =>
    patternsApi.setOccasionVerdict(patternId, occasionId, verdict));
}

export function usePatternVerdict(patternId: string) {
  return useRefreshing((verdict: PatternVerdictValue) => patternsApi.setPatternVerdict(patternId, verdict));
}

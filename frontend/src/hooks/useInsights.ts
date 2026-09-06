import { useQuery } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import * as insightsApi from '@/api/insights';

export function useInsights() {
  return useQuery({ queryKey: qk.insights, queryFn: insightsApi.listInsights });
}

export function useInsight(id: string | undefined) {
  return useQuery({
    queryKey: id ? qk.insight(id) : ['noop'],
    queryFn:  () => insightsApi.getInsight(id!),
    enabled:  !!id,
  });
}

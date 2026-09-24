import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import * as decisionsApi from '@/api/decisions';
import type { DecisionCreate, DecisionOutcome } from '@/types/api';

export function useDecisions() {
  return useQuery({ queryKey: qk.decisions, queryFn: decisionsApi.getDecisions });
}

/** Record a decision; the list refetches so it shows what the server stored. */
export function useCreateDecision() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: DecisionCreate) => decisionsApi.createDecision(input),
    onSettled: () => { qc.invalidateQueries({ queryKey: qk.decisions }); },
  });
}

export function useRecordOutcome() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: DecisionOutcome & { id: string }) =>
      decisionsApi.recordOutcome(id, input),
    onSettled: () => { qc.invalidateQueries({ queryKey: qk.decisions }); },
  });
}

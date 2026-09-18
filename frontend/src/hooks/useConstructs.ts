import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import {
  confirmConstruct, discoverConstructs, listCandidates, rejectConstruct,
} from '@/api/constructs';

/** Patterns awaiting a decision. Nothing here is measured until confirmed. */
export const useConstructCandidates = () => useQuery({
  queryKey: qk.constructs,
  queryFn: listCandidates,
});

/**
 * Reading the whole archive. This is the one action that sends the journal to
 * the model, so it is a mutation the owner triggers — never a background fetch.
 */
export function useDiscoverConstructs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (includeStaged: boolean) => discoverConstructs(includeStaged),
    onSuccess: () => { qc.invalidateQueries({ queryKey: qk.constructs }); },
  });
}

export function useConfirmConstruct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => confirmConstruct(id),
    onSuccess: () => {
      // Confirming writes occurrences, so the insights it now feeds are stale.
      qc.invalidateQueries({ queryKey: qk.constructs });
      qc.invalidateQueries({ queryKey: qk.insights });
    },
  });
}

export function useRejectConstruct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => rejectConstruct(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: qk.constructs }); },
  });
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import * as importApi from '@/api/importing';
import type { ImportBatch } from '@/types/api';

/** True while the server is still doing something we are waiting on. */
export function isBusy(batch?: ImportBatch): boolean {
  return !!batch && (batch.status === 'parsing' || batch.status === 'committing');
}

export const useImportAdapters = () =>
  useQuery({ queryKey: qk.importAdapters, queryFn: importApi.listAdapters, staleTime: Infinity });

export const useImportBatches = () =>
  useQuery({ queryKey: qk.importBatches, queryFn: importApi.listBatches });

/**
 * Poll while the batch is mid-flight.
 *
 * Polling rather than SSE, on purpose: the work outlives the request that
 * started it — parsing and committing happen on the queue — so there is no
 * response to stream, and a dropped connection must not lose it. A closed tab
 * costs nothing here, and reopening the page just resumes.
 */
export const useImportBatch = (id: string | undefined) =>
  useQuery({
    queryKey: id ? qk.importBatch(id) : ['noop'],
    queryFn: () => importApi.getBatch(id!),
    enabled: !!id,
    refetchInterval: (q) => (isBusy(q.state.data) ? 1500 : false),
  });

export const useImportEntries = (id: string | undefined, live: boolean) =>
  useQuery({
    queryKey: id ? qk.importEntries(id) : ['noop'],
    queryFn: () => importApi.listEntries(id!),
    enabled: !!id,
    // Audio entries fill in as their transcripts land.
    refetchInterval: live ? 2000 : false,
  });

export function useImportActions(batchId: string | undefined) {
  const qc = useQueryClient();
  const refresh = () => {
    if (!batchId) return;
    qc.invalidateQueries({ queryKey: qk.importBatch(batchId) });
    qc.invalidateQueries({ queryKey: qk.importEntries(batchId) });
  };

  return {
    setDate: useMutation({
      mutationFn: (v: { id: string; occurredOn: string }) =>
        importApi.updateEntry(v.id, { occurredOn: v.occurredOn }),
      onSuccess: refresh,
    }),
    setStatus: useMutation({
      mutationFn: (v: { id: string; status: 'staged' | 'excluded' }) =>
        importApi.updateEntry(v.id, { status: v.status }),
      onSuccess: refresh,
    }),
    bulk: useMutation({
      mutationFn: (v: { ids: string[]; op: 'exclude' | 'include' | 'set_date' | 'use_file_date' | 'accept_unknown_date' | 'require_date'; occurredOn?: string }) =>
        importApi.bulkUpdate(v.ids, v.op, v.occurredOn),
      onSuccess: refresh,
    }),
    reparse: useMutation({
      mutationFn: (adapter: string) => importApi.reparse(batchId!, adapter),
      onSuccess: refresh,
    }),
    commit: useMutation({
      mutationFn: () => importApi.commit(batchId!),
      onSuccess: () => {
        refresh();
        // Imported entries are journal entries now, and the analytical layer
        // will have more to say once the queue catches up.
        qc.invalidateQueries({ queryKey: qk.journal });
        qc.invalidateQueries({ queryKey: qk.insights });
        qc.invalidateQueries({ queryKey: qk.importBatches });
      },
    }),
    discard: useMutation({
      mutationFn: (withReflections: boolean) => importApi.discard(batchId!, withReflections),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: qk.importBatches });
        qc.invalidateQueries({ queryKey: qk.journal });
      },
    }),
  };
}

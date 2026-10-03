import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import * as sessionsApi from '@/api/sessions';
import type { SessionImportChanges } from '@/api/sessions';

/** Polls while a voices pass is under way: it runs on the queue and takes minutes. */
export const useSessionImports = () =>
  useQuery({
    queryKey: qk.sessionImports,
    queryFn: sessionsApi.listSessionImports,
    refetchInterval: (q) => ((q.state.data ?? []).some(item =>
      item.voices.status === 'queued' || item.voices.status === 'running') ? 4000 : false),
  });

/** Every change to a staged session refreshes the list, and an import or undo the journal too. */
export function useSessionImportActions() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: qk.sessionImports });
  const refreshAll = () => { refresh(); qc.invalidateQueries({ queryKey: qk.journal }); };
  return {
    update: useMutation({
      mutationFn: (v: { id: string; changes: SessionImportChanges }) =>
        sessionsApi.updateSessionImport(v.id, v.changes),
      onSuccess: refresh,
    }),
    commit: useMutation({ mutationFn: sessionsApi.commitSessionImport, onSuccess: refreshAll }),
    undo: useMutation({ mutationFn: sessionsApi.undoSessionImport, onSuccess: refreshAll }),
    discard: useMutation({ mutationFn: sessionsApi.discardSessionImport, onSuccess: refresh }),
    addRecording: useMutation({
      mutationFn: (v: { id: string; file: File }) => sessionsApi.uploadSessionRecording(v.id, v.file),
      onSuccess: refresh,
    }),
    startVoices: useMutation({ mutationFn: sessionsApi.startSessionVoices, onSuccess: refresh }),
    undoVoices: useMutation({ mutationFn: sessionsApi.undoSessionVoices, onSuccess: refresh }),
  };
}

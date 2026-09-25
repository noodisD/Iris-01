import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as ideasApi from '@/api/ideas';
import { qk } from '@/lib/queryClient';
import type { ConfirmIdeaBody, IdeaDomain, IdeaPosition } from '@/types/api';

const fresh = { staleTime: 0, refetchOnMount: 'always' as const, refetchOnWindowFocus: true };

export function useIdeasFramework() {
  return useQuery({
    queryKey: qk.ideasFramework,
    queryFn: ideasApi.getIdeasFramework,
    ...fresh,
    refetchInterval: query => query.state.data?.lastRun?.status === 'running' ? 3000 : false,
  });
}

export function useIdeaReview() {
  return useQuery({
    queryKey: qk.ideaReview,
    queryFn: ideasApi.getIdeaReview,
    ...fresh,
    refetchInterval: query => query.state.data?.lastRun?.status === 'running' ? 3000 : false,
  });
}

export function useIdea(id: string | undefined) {
  return useQuery({
    queryKey: id ? qk.idea(id) : ['ideas', 'missing'],
    queryFn: () => ideasApi.getIdea(id!),
    enabled: !!id,
    ...fresh,
  });
}

function useIdeaMutation<T>(mutationFn: (value: T) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: () => { qc.invalidateQueries({ queryKey: qk.ideas }); },
  });
}

export function useDiscoverIdeas() {
  return useIdeaMutation(() => ideasApi.discoverIdeas());
}

export function useMeaningEstimate(enabled: boolean) {
  return useQuery({ queryKey: [...qk.ideas, 'meaning-estimate'], queryFn: ideasApi.getMeaningEstimate, enabled, staleTime: 0 });
}

export function useDiscoverMeanings() {
  return useIdeaMutation(() => ideasApi.discoverMeanings());
}

export function useConfirmIdea() {
  return useIdeaMutation(({ id, body }: { id: string; body: ConfirmIdeaBody }) => ideasApi.confirmIdea(id, body));
}

export function useRejectIdea() {
  return useIdeaMutation((id: string) => ideasApi.rejectIdea(id));
}

export function useRejectIdeaCitations() {
  return useIdeaMutation(({ id, citationIds }: { id: string; citationIds: string[] }) => (
    ideasApi.rejectIdeaCitations(id, citationIds)
  ));
}

export function useUpdateIdea() {
  return useIdeaMutation(({ id, body }: { id: string; body: { position?: IdeaPosition; domain?: IdeaDomain } }) => (
    ideasApi.updateIdea(id, body)
  ));
}

export function useDiscoverIdeaLinks() {
  return useIdeaMutation((id: string) => ideasApi.discoverIdeaLinks(id));
}

export function useConfirmIdeaLink() {
  return useIdeaMutation((id: string) => ideasApi.confirmIdeaLink(id));
}

export function useRejectIdeaLink() {
  return useIdeaMutation((id: string) => ideasApi.rejectIdeaLink(id));
}

export function useCritiqueIdea() {
  return useIdeaMutation((id: string) => ideasApi.critiqueIdea(id));
}

import { useQuery } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import { getBodyOverview } from '@/api/body';
import { getLatestWeek } from '@/api/review';
import { listJournal } from '@/api/journal';
import { getUser, getKnownFacts, getConnectors } from '@/api/settings';

export const useBody       = () => useQuery({ queryKey: qk.body,       queryFn: getBodyOverview });
export const useReview     = () => useQuery({ queryKey: qk.review,     queryFn: getLatestWeek   });
export const useJournal    = () => useQuery({ queryKey: qk.journal,    queryFn: () => listJournal() });
export const useUser       = () => useQuery({ queryKey: qk.user,       queryFn: getUser });
export const useKnowledge  = () => useQuery({ queryKey: qk.knowledge,  queryFn: getKnownFacts });
export const useConnectors = () => useQuery({ queryKey: qk.connectors, queryFn: getConnectors });

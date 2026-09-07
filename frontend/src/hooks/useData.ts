import { useQuery } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import { getLatestWeek } from '@/api/review';
import { listJournal } from '@/api/journal';
import { getUser, getKnownFacts, getConnectors, getAnalysisPreferences } from '@/api/settings';
import { getOnboarding } from '@/api/onboarding';

export const useOnboarding = () => useQuery({ queryKey: qk.onboarding, queryFn: getOnboarding });
export const useReview     = () => useQuery({ queryKey: qk.review,     queryFn: getLatestWeek   });
export const useJournal    = () => useQuery({ queryKey: qk.journal,    queryFn: () => listJournal() });
export const useUser       = () => useQuery({ queryKey: qk.user,       queryFn: getUser });
export const useKnowledge  = () => useQuery({ queryKey: qk.knowledge,  queryFn: getKnownFacts });
export const useConnectors = () => useQuery({ queryKey: qk.connectors, queryFn: getConnectors });
export const useAnalysisPreferences = () => useQuery({ queryKey: qk.analysis, queryFn: getAnalysisPreferences });

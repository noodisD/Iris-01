import type { DiscoveryRange } from '@/types/api';
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export const qk = {
  conversation: ['conversation', 'current'] as const,
  messages: (id: string) => ['conversation', id, 'messages'] as const,
  habits: ['habits', 'today'] as const,
  journal: ['journal'] as const,
  constructs: ['constructs', 'candidates'] as const,
  lastRun: ['constructs', 'last-run'] as const,
  ideas: ['ideas'] as const,
  ideasFramework: ['ideas', 'framework'] as const,
  ideaReview: ['ideas', 'review'] as const,
  idea: (id: string) => ['ideas', id] as const,
  onboarding: ['onboarding'] as const,
  user: ['user'] as const,
  knowledge: ['knowledge'] as const,
  analysis: ['user', 'analysis'] as const,
  mobileConnection: ['mobile', 'connection'] as const,
  importAdapters: ['import', 'adapters'] as const,
  importBatches: ['import', 'batches'] as const,
  importBatch: (id: string) => ['import', 'batches', id] as const,
  sessionImports: ['sessions', 'imports'] as const,
  questionnaire: ['questionnaire'] as const,
  questionnaireEstimate: (id: string) => ['questionnaire', 'estimate', id] as const,
  questionnaireHistory: (id: string) => ['questionnaire', 'history', id] as const,
  importEntries: (id: string) => ['import', 'batches', id, 'entries'] as const,
  sensorBatches: ['sensors', 'batches'] as const,
  sensorBatch: (id: number | string) => ['sensors', 'batches', String(id)] as const,
  review: ['review', 'latest'] as const,
  decisions: ['decisions'] as const,
  patterns: ['patterns'] as const,
  pattern: (id: string, period: DiscoveryRange = 'all') => ['patterns', 'detail', id, period] as const,
  summaries: (period: DiscoveryRange) => ['patterns', 'summaries', period] as const,
  insights: (period: DiscoveryRange) => ['patterns', 'insights', period] as const,
  insight: (id: string, period: DiscoveryRange) => ['patterns', 'insight', id, period] as const,
  discoveryStatus: ['patterns', 'status'] as const,
  dayDifferencesRoot: ['day-differences'] as const,
  dayDifferences: (period: DiscoveryRange) => ['day-differences', period] as const,
  dayDifferenceDetail: (outcome: string, split: string, period: DiscoveryRange, snapshot: string) =>
    ['day-differences', 'detail', outcome, split, period, snapshot] as const,
  observatory: (part: string, ...args: unknown[]) => ['observatory', part, ...args] as const,
};

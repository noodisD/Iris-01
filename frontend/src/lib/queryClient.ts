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
  inferred: (id: string) => ['conversation', id, 'inferred'] as const,
  habits: ['habits', 'today'] as const,
  insights: ['insights'] as const,
  insight: (id: string) => ['insights', id] as const,
  journal: ['journal'] as const,
  onboarding: ['onboarding'] as const,
  user: ['user'] as const,
  knowledge: ['knowledge'] as const,
  connectors: ['connectors'] as const,
  analysis: ['user', 'analysis'] as const,
  review: ['review', 'latest'] as const,
};

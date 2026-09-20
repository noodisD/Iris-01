import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import * as habitsApi from '@/api/habits';
import type { HabitsTodayResponse } from '@/types/api';

export function useHabits() {
  return useQuery({ queryKey: qk.habits, queryFn: habitsApi.getHabitsToday });
}

/** Optimistic toggle — UI flips instantly, server confirms in the background. */
export function useToggleHabit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, done }: { id: string; done: boolean }) =>
      habitsApi.toggleHabit({ habitId: id, done }),
    onMutate: async ({ id, done }) => {
      await qc.cancelQueries({ queryKey: qk.habits });
      const previous = qc.getQueryData<HabitsTodayResponse>(qk.habits);
      qc.setQueryData<HabitsTodayResponse>(qk.habits, (old) =>
        old ? {
          ...old,
          habits: old.habits.map(h => h.id === id ? { ...h, doneToday: done, streakDays: done ? h.streakDays + 1 : Math.max(0, h.streakDays - 1) } : h),
          doneCount: old.habits.filter(h => (h.id === id ? done : h.doneToday)).length,
        } : old,
      );
      return { previous };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) qc.setQueryData(qk.habits, ctx.previous);
    },
    onSuccess: (server) => {
      qc.setQueryData<HabitsTodayResponse>(qk.habits, (old) =>
        old ? { ...old, habits: old.habits.map(h => h.id === server.id ? server : h) } : old,
      );
    },
    // The row is the server's word; the aggregates beside it — consistency,
    // longest streak — are computed across every habit, and showing yesterday's
    // totals next to today's tick is two answers to one question.
    onSettled: () => { qc.invalidateQueries({ queryKey: qk.habits }); },
  });
}

/** Add a habit; the list refetches so its streak and colour come from the server. */
export function useCreateHabit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: habitsApi.createHabit,
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.habits }),
  });
}

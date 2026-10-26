import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import * as habitsApi from '@/api/habits';
import type { Habit, HabitDay, HabitsTodayResponse } from '@/types/api';

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
    onSettled: () => { qc.invalidateQueries({ queryKey: ['habits'] }); },
  });
}

/** Add a habit; the list refetches so its streak and colour come from the server. */
export function useCreateHabit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: habitsApi.createHabit,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.habits });
      void qc.invalidateQueries({ queryKey: ['habits'] });
    },
  });
}

/** Every habit, archived included, for the Habits pages. */
export function useAllHabits() {
  return useQuery({ queryKey: ['habits', 'all'], queryFn: habitsApi.listHabits });
}

export function useHabitDays(id: string | undefined, start: string, end: string) {
  return useQuery({
    queryKey: ['habits', 'days', id, start, end],
    queryFn: () => habitsApi.getHabitDays(id!, start, end),
    enabled: !!id,
  });
}

/** Any change to a habit or a day refreshes every habit view: streaks and today's ticks move with it. */
function useHabitsRefresh() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ['habits'] });
    void qc.invalidateQueries({ queryKey: qk.habits });
  };
}

export function useSetHabitDay(id: string) {
  const refresh = useHabitsRefresh();
  return useMutation({
    mutationFn: ({ date, status, note }: { date: string; status: HabitDay['status']; note: string | null }) =>
      habitsApi.setHabitDay(id, date, status, note),
    onSuccess: refresh,
  });
}

export function useUpdateHabit(id: string) {
  const refresh = useHabitsRefresh();
  return useMutation({ mutationFn: (update: habitsApi.HabitUpdate) => habitsApi.updateHabit(id, update), onSuccess: refresh });
}

export function useDeleteHabit(id: string) {
  const refresh = useHabitsRefresh();
  return useMutation({ mutationFn: () => habitsApi.deleteHabit(id), onSuccess: refresh });
}

/** Move habits in one tab; the list moves at once and the server keeps the order. */
export function useOrderHabits() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => habitsApi.orderHabits(ids),
    onMutate: async (ids: string[]) => {
      await qc.cancelQueries({ queryKey: ['habits', 'all'] });
      const previous = qc.getQueryData<Habit[]>(['habits', 'all']);
      if (previous) {
        const moved = new Set(ids);
        const byId = new Map(previous.map(h => [h.id, h]));
        const queue = ids.map(id => byId.get(id)!).filter(Boolean);
        qc.setQueryData<Habit[]>(['habits', 'all'], previous.map(h => (moved.has(h.id) ? queue.shift()! : h)));
      }
      return { previous };
    },
    onError: (_e, _ids, ctx) => { if (ctx?.previous) qc.setQueryData(['habits', 'all'], ctx.previous); },
    onSettled: () => { void qc.invalidateQueries({ queryKey: ['habits'] }); },
  });
}

/**
 * Mark one day done or not done straight from its dot (a double-click). The day's
 * note is kept; the dot changes at once and the server's streak follows.
 */
export function useToggleHabitDay() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, date, done }: { id: string; date: string; done: boolean }) =>
      habitsApi.toggleHabit({ habitId: id, done, date }),
    onMutate: async ({ id, date, done }) => {
      await qc.cancelQueries({ queryKey: ['habits', 'all'] });
      const previous = qc.getQueryData<Habit[]>(['habits', 'all']);
      qc.setQueryData<Habit[]>(['habits', 'all'], old => old?.map(h => {
        if (h.id !== id || !h.recentStart || !h.recentStatus) return h;
        const index = Math.round((new Date(`${date}T12:00:00`).getTime()
          - new Date(`${h.recentStart}T12:00:00`).getTime()) / 86400000);
        if (index < 0 || index >= h.recentStatus.length) return h;
        const recentStatus = [...h.recentStatus];
        recentStatus[index] = done ? 'done' : 'none';
        return { ...h, recentStatus };
      }));
      return { previous };
    },
    onError: (_e, _v, ctx) => { if (ctx?.previous) qc.setQueryData(['habits', 'all'], ctx.previous); },
    onSettled: () => { void qc.invalidateQueries({ queryKey: ['habits'] }); },
  });
}

/**
 * Habits API — WIRED LIVE (single-user backend).
 *
 * Backend endpoints (iris_api.py):
 *   GET    /api/habits/today                → HabitsTodayResponse
 *   POST   /api/habits/:id/toggle           → Habit  (request body: { done, date? })
 *   POST   /api/habits                      → Habit  (create)
 */

import { api } from './client';
import type { Habit, HabitsTodayResponse, HabitToggleRequest } from '@/types/api';

export async function getHabitsToday(): Promise<HabitsTodayResponse> {
  return api.get('/habits/today');
}

export async function toggleHabit(req: HabitToggleRequest): Promise<Habit> {
  return api.post(`/habits/${req.habitId}/toggle`, { done: req.done, date: req.date });
}

/** Only the name is required; the server fills the tag and colour it is not given. */
export type HabitCreate = Pick<Habit, 'name'> & Partial<Pick<Habit, 'tag' | 'intent' | 'color'>>;

export async function createHabit(input: HabitCreate): Promise<Habit> {
  return api.post('/habits', input);
}

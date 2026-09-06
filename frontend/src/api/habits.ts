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

export async function createHabit(input: Pick<Habit, 'name' | 'tag' | 'intent' | 'color'>): Promise<Habit> {
  return api.post('/habits', input);
}

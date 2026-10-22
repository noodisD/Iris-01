/**
 * Habits API — WIRED LIVE (single-user backend).
 *
 * Backend endpoints (iris_api.py):
 *   GET    /api/habits/today                → HabitsTodayResponse
 *   POST   /api/habits/:id/toggle           → Habit  (request body: { done, date? })
 *   POST   /api/habits                      → Habit  (create)
 */

import { api } from './client';
import type { Habit, HabitDay, HabitFrequency, HabitsTodayResponse, HabitToggleRequest } from '@/types/api';

export async function getHabitsToday(): Promise<HabitsTodayResponse> {
  return api.get('/habits/today');
}

export async function toggleHabit(req: HabitToggleRequest): Promise<Habit> {
  return api.post(`/habits/${req.habitId}/toggle`, { done: req.done, date: req.date });
}

/** Only the name is required; the server fills the tag and colour it is not given. */
export type HabitCreate = Pick<Habit, 'name'> & Partial<Pick<Habit, 'tag' | 'intent' | 'frequency' | 'target'>>;

/** Every habit, archived ones included. */
export function listHabits(): Promise<Habit[]> {
  return api.get('/habits');
}

export interface HabitUpdate {
  name?: string; intent?: string | null; tag?: string | null;
  frequency?: HabitFrequency; target?: number; archived?: boolean;
}

export function updateHabit(id: string, update: HabitUpdate): Promise<Habit> {
  return api.patch(`/habits/${id}`, update);
}

/** Deletes the habit and its whole history; archiving keeps the history. */
export function deleteHabit(id: string): Promise<{ deleted: boolean }> {
  return api.del(`/habits/${id}`);
}

export function getHabitDays(id: string, start: string, end: string): Promise<HabitDay[]> {
  return api.get(`/habits/${id}/days?start=${start}&end=${end}`);
}

/** Mark any past day done, skipped or neither, with a note. */
export function setHabitDay(id: string, date: string, status: HabitDay['status'], note: string | null):
  Promise<{ day: HabitDay; habit: Habit }> {
  return api.put(`/habits/${id}/days/${date}`, { status, note });
}

export async function createHabit(input: HabitCreate): Promise<Habit> {
  return api.post('/habits', input);
}

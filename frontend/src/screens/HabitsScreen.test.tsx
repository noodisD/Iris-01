/**
 * Habits: daily, weekly and monthly tabs; any past day can be fixed with a note;
 * a habit can be edited, archived or deleted. Every habit here is invented.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Habit, HabitDay } from '@/types/api';

const server = vi.hoisted(() => ({
  habits: [] as Habit[], created: [] as unknown[], days: [] as unknown[][], updates: [] as unknown[][],
  deleted: [] as string[],
}));

const habit = (over: Partial<Habit>): Habit => ({
  id: '1', userId: '1', name: 'Water the allotment', tag: '', intent: undefined, color: 'sage',
  streakDays: 2, bestStreak: 4, doneToday: false, recentDays: [], frequency: 'daily', target: 1,
  streakUnit: 'day', periodDone: 0, periodMet: false, periods: [], archived: false, createdAt: '2026-09-01', ...over,
});

vi.mock('@/api/habits', () => ({
  listHabits: async () => server.habits,
  getHabitsToday: async () => ({ habits: server.habits, doneCount: 0, totalCount: 0, consistency30d: 0, longestActiveStreak: 0 }),
  toggleHabit: vi.fn(),
  createHabit: async (input: Partial<Habit>) => {
    server.created.push(input);
    const made = habit({ id: String(server.habits.length + 1), name: input.name!, tag: input.tag ?? '',
      frequency: input.frequency, target: input.target });
    server.habits = [...server.habits, made];
    return made;
  },
  getHabitDays: async (): Promise<HabitDay[]> => [{ date: '2026-10-03', status: 'done', note: 'Before the rain.' }],
  setHabitDay: async (id: string, date: string, status: string, note: string | null) => {
    server.days.push([id, date, status, note]);
    return { day: { date, status, note }, habit: server.habits[0] };
  },
  updateHabit: async (id: string, update: object) => {
    server.updates.push([id, update]);
    server.habits = server.habits.map(h => (h.id === id ? { ...h, ...update } as Habit : h));
    return server.habits.find(h => h.id === id);
  },
  deleteHabit: async (id: string) => { server.deleted.push(id); server.habits = server.habits.filter(h => h.id !== id); return { deleted: true }; },
}));

import { HabitsScreen } from './HabitsScreen';
import { HabitDetailScreen } from './HabitDetailScreen';

function show(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/habits/:period" element={<HabitsScreen />} />
    <Route path="/habits/:period/:id" element={<HabitDetailScreen />} />
  </Routes></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => { server.habits = []; server.created = []; server.days = []; server.updates = []; server.deleted = []; });

describe('the habit lists', () => {
  it('says there are none yet, then lists the one just named', async () => {
    show('/habits/daily');
    expect(await screen.findByText(/No daily habits yet/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Habit name'), { target: { value: 'Tactics puzzles' } });
    fireEvent.change(screen.getByLabelText('Tag'), { target: { value: 'chess' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add habit' }));
    expect(await screen.findByText('Tactics puzzles')).toBeInTheDocument();
    expect(server.created).toEqual([{ name: 'Tactics puzzles', tag: 'chess', frequency: 'daily', target: 1 }]);
  });

  it('cannot add a habit with no name', async () => {
    show('/habits/daily');
    await screen.findByText(/No daily habits yet/);
    expect(screen.getByRole('button', { name: 'Add habit' })).toBeDisabled();
  });

  it('keeps weekly habits on their own tab, with progress towards the target', async () => {
    server.habits = [habit({ id: '1', name: 'Morning pages' }),
      habit({ id: '2', name: 'Long walk', frequency: 'weekly', target: 3, periodDone: 1, streakUnit: 'week' })];
    show('/habits/weekly');
    expect(await screen.findByText('Long walk')).toBeInTheDocument();
    expect(screen.queryByText('Morning pages')).toBeNull();
    expect(screen.getByText('1 of 3 this week')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Habit name'), { target: { value: 'Call home' } });
    fireEvent.change(screen.getByLabelText('Times a week'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add habit' }));
    await waitFor(() => expect(server.created).toEqual([{ name: 'Call home', tag: undefined, frequency: 'weekly', target: 2 }]));
  });
});

describe('a habit page', () => {
  it('fixes a forgotten day with a note, and never a future one', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-22T12:00:00'));
    server.habits = [habit({})];
    show('/habits/daily/1');
    const grid = await screen.findByRole('grid');
    expect(await within(grid).findByRole('gridcell', { name: /^3: done, with a note/ })).toBeInTheDocument();
    expect(within(grid).getByRole('gridcell', { name: /^23:/ })).toBeDisabled();
    fireEvent.click(within(grid).getByRole('gridcell', { name: /^20:/ }));
    fireEvent.click(screen.getByRole('radio', { name: 'Done' }));
    fireEvent.change(screen.getByLabelText('Note for this day'), { target: { value: 'Late, but done.' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save day' })); });
    expect(server.days).toEqual([['1', '2026-10-20', 'done', 'Late, but done.']]);
    vi.useRealTimers();
  });

  it('edits the habit, and deletes it only after asking', async () => {
    server.habits = [habit({})];
    show('/habits/daily/1');
    const name = await screen.findByLabelText('Name');
    fireEvent.change(name, { target: { value: 'Water the beans' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save changes' })); });
    expect(server.updates[0]).toEqual(['1', { name: 'Water the beans', intent: null, tag: null, frequency: 'daily' }]);
    fireEvent.click(screen.getByRole('button', { name: 'Delete…' }));
    expect(server.deleted).toEqual([]);
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Delete for good' })); });
    expect(server.deleted).toEqual(['1']);
  });
});

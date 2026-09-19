/**
 * A habit can be started from the screen that lists them.
 *
 * `createHabit` existed and nothing called it, so the list could only hold
 * habits made somewhere else — and an empty list drew an empty constellation.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Habit, HabitsTodayResponse } from '@/types/api';

const server = vi.hoisted(() => ({ habits: [] as Habit[], created: [] as unknown[] }));

vi.mock('@/api/habits', () => ({
  getHabitsToday: async (): Promise<HabitsTodayResponse> => ({
    habits: server.habits, doneCount: 0, totalCount: server.habits.length,
    consistency30d: 0, longestActiveStreak: 0,
  } as HabitsTodayResponse),
  toggleHabit: vi.fn(),
  createHabit: async (input: { name: string; tag?: string }) => {
    server.created.push(input);
    const habit = { id: '1', name: input.name, tag: input.tag ?? 'general', intent: null,
                    color: 'sage', streakDays: 0, bestStreak: 0, doneToday: false,
                    recentDays: [] } as unknown as Habit;
    server.habits = [habit];
    return habit;
  },
}));

import { HabitsScreen } from './HabitsScreen';

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><HabitsScreen /></QueryClientProvider>);
}

describe('adding a habit', () => {
  beforeEach(() => { server.habits = []; server.created = []; });

  it('says there are none yet, then lists the one just named', async () => {
    show();
    expect(await screen.findByText(/No habits yet/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Habit name'), { target: { value: 'Tactics puzzles' } });
    fireEvent.change(screen.getByLabelText('Tag'), { target: { value: 'chess' } });
    fireEvent.click(screen.getByRole('button', { name: '+ add habit' }));

    expect(await screen.findByText('Tactics puzzles')).toBeInTheDocument();
    expect(server.created).toEqual([{ name: 'Tactics puzzles', tag: 'chess' }]);
    await waitFor(() => expect(screen.queryByText(/No habits yet/)).toBeNull());
    expect(screen.getByLabelText('Habit name')).toHaveValue('');
  });

  it('cannot add a habit with no name', async () => {
    show();
    await screen.findByText(/No habits yet/);
    expect(screen.getByRole('button', { name: '+ add habit' })).toBeDisabled();
  });
});

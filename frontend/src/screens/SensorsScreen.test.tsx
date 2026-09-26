/**
 * Sensors: measured days in a table, readings waiting for review in their own
 * tab, and places listed with their own edit and remove actions.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DayFeature, Place } from '@/api/days';

const server = vi.hoisted(() => ({ places: [] as Place[], removed: [] as number[] }));

vi.mock('@/api/sensors', () => ({
  listBatches: async () => [{ id: 1, source: 'pixel', status: 'pending', review_day: '2026-01-05',
    received_at: '2026-01-05T20:00:00Z', observation_count: 3, dropped_count: 0, theme_links: {} }],
  getBatch: vi.fn(), confirmBatch: vi.fn(), rejectBatch: vi.fn(), deleteBatch: vi.fn(),
}));
vi.mock('@/api/days', () => ({
  listDays: async () => ({ days: [{ day: '2026-01-05', dayKind: 'workday', homeMinutes: 600, officeMinutes: 480,
    commuteMinutes: 45, commuteMode: null, steps: 8000, stepsFullDay: true, screenMinutes: 95,
    screenByCategory: {}, sleepMinutes: null, locationCoverage: 0.9 } satisfies DayFeature] }),
  listCategories: async () => ({ categories: [] }),
  listPlaces: async () => ({ places: server.places }),
  suggestPlaces: async () => ({}),
  deletePlace: async (id: number) => { server.removed.push(id); server.places = []; return { status: 'ok' }; },
  createPlace: vi.fn(), updatePlace: vi.fn(), saveCategory: vi.fn(), uploadTimeline: vi.fn(), confirmTimelineRange: vi.fn(),
}));

import { SensorsScreen } from './SensorsScreen';

function show(path = '/sensors') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><SensorsScreen /></MemoryRouter></QueryClientProvider>);
}

describe('sensors', () => {
  beforeEach(() => {
    server.places = [{ id: 4, name: 'Studio', kind: 'other', lat: 1, lon: 2, radiusM: 150, source: 'owner' }];
    server.removed = [];
  });

  it('shows measured days as a table, in hours and minutes', async () => {
    show();
    const table = await screen.findByRole('region', { name: 'Days' });
    expect(within(table).getByText('10h 00m')).toBeInTheDocument();
    expect(within(table).getByText('90%')).toBeInTheDocument();
  });

  it('counts the batches waiting for review on their tab', async () => {
    show();
    const tab = await screen.findByRole('tab', { name: 'To review (1)' });
    fireEvent.mouseDown(tab);
    expect(await screen.findByRole('button', { name: /Pixel, 2026-01-05/ })).toBeInTheDocument();
  });

  it('removes a place from its own row', async () => {
    show('/sensors?view=location');
    fireEvent.click(await screen.findByRole('button', { name: 'Remove Studio' }));
    expect(await screen.findByText('No places yet.')).toBeInTheDocument();
    expect(server.removed).toEqual([4]);
  });
});

/**
 * The journal records what the owner said, and nothing it made up for them.
 *
 * Energy is unset until chosen. An entry whose day is unknown reads as undated
 * rather than as the day it was imported. The editor is mocked so the suite
 * does not load CodeMirror.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { JournalEntry } from '@/types/api';

const sent = vi.hoisted(() => ({ calls: [] as unknown[] }));
const entries = vi.hoisted(() => ({ list: [] as JournalEntry[] }));

vi.mock('@/api/journal', () => ({
  createEntry: async (input: unknown) => { sent.calls.push(input); return {} as JournalEntry; },
  listJournal: async () => ({ entries: entries.list, recurringPhrases: [] }),
}));

vi.mock('@/components/journal/MarkdownEditor', () => ({
  MarkdownEditor: ({
    value,
    onChange,
  }: {
    value: string;
    onChange: (text: string) => void;
  }) => (
    <textarea data-testid="journal-editor" aria-label="journal entry" value={value} onChange={event => onChange(event.target.value)} />
  ),
}));

import { JournalScreen } from './JournalScreen';

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><JournalScreen /></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => { sent.calls = []; entries.list = []; });

describe('writing an entry', () => {
  it('records no check-in unless one was chosen', async () => {
    show();
    fireEvent.change(await screen.findByTestId('journal-editor'), {
      target: { value: 'a quiet morning' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    expect(sent.calls).toEqual([{ text: 'a quiet morning', format: 'markdown' }]);
  });

  it('sends the energy the owner chose', async () => {
    show();
    fireEvent.change(await screen.findByTestId('journal-editor'), {
      target: { value: 'a good day' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'energy 8' }));
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    expect(sent.calls).toEqual([{
      text: 'a good day',
      format: 'markdown',
      checkin: { energy: 8 },
    }]);
  });

  it('can save a check-in with no prose', async () => {
    show();
    fireEvent.click(await screen.findByRole('button', { name: 'focus 4' }));
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    expect(sent.calls).toEqual([{ text: '', format: 'markdown', checkin: { focus: 4 } }]);
  });
});

describe('an entry with no day', () => {
  it('says undated rather than the day it was imported', async () => {
    entries.list = [{
      id: '7', userId: '1', lines: ['from a recording'], tags: [],
      occurredOn: null, importedAt: '2026-09-19T10:00:00Z', createdAt: null,
    } as unknown as JournalEntry];
    show();

    expect(await screen.findByText('undated')).toBeInTheDocument();
  });
});

describe('an entry that came from a recording', () => {
  it('offers the recording beside its transcript', async () => {
    entries.list = [{
      id: '9', userId: '1', lines: ['what the recording said'], tags: [],
      occurredOn: '2024-03-02', importedAt: '2026-09-19T10:00:00Z',
      createdAt: '2024-03-02', audioUrl: '/api/audio/9',
    } as unknown as JournalEntry];
    show();

    const player = await screen.findByLabelText('the recording this was transcribed from');
    expect(player).toHaveAttribute('src', '/api/audio/9');
  });
});

describe('a markdown entry', () => {
  it('shows the heading and the bold words without the markers', async () => {
    entries.list = [{
      id: '3', userId: '1', lines: ['# Soup', '', '**Basil** and salt.'],
      text: '# Soup\n\n**Basil** and salt.', format: 'markdown', tags: [],
      occurredOn: '2026-01-02', createdAt: '2026-01-02',
    } as unknown as JournalEntry];
    show();

    expect(await screen.findByRole('heading', { name: 'Soup' })).toBeInTheDocument();
    expect(screen.getByText('Basil')).toBeInTheDocument();
    expect(screen.queryByText('**Basil**')).not.toBeInTheDocument();
  });
});

/**
 * Writing in another language shows the English IRIS reads, with the original
 * one tap away (ADR-0036). Every line here is invented.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { JournalEntry } from '@/types/api';
import { EntryBody } from './EntryBody';

const entry = (extra: Partial<JournalEntry> = {}): JournalEntry => ({
  id: '1', userId: '1', lines: [], text: 'Zagrałam dziś obronę sycylijską.', format: 'plain',
  occurredOn: '2026-03-03', createdAt: null, ...extra,
});

describe('an entry in another language', () => {
  it('shows the English first and the original on request', () => {
    render(<EntryBody entry={entry({ translation: { text: 'Today I played the Sicilian.', from: 'pl' } })} />);
    expect(screen.getByText('Today I played the Sicilian.')).toBeInTheDocument();
    expect(screen.getByText(/Translated from Polish/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show the Polish' }));
    expect(screen.getByText('Zagrałam dziś obronę sycylijską.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show the English' }));
    expect(screen.getByText('Today I played the Sicilian.')).toBeInTheDocument();
  });

  it('shows English writing as it is, with no language line', () => {
    render(<EntryBody entry={entry({ text: 'Played the Sicilian.' })} />);
    expect(screen.getByText('Played the Sicilian.')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

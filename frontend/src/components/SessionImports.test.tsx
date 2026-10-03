/**
 * A session cannot be imported until the owner has said when it was and which
 * speaker they are, and the cost is shown before the click (ADR-0028).
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SessionImport } from '@/types/api';

const state = vi.hoisted(() => ({ items: [] as SessionImport[], calls: [] as [string, unknown][] }));

vi.mock('@/hooks/useSessionImports', () => ({
  useSessionImports: () => ({ data: state.items }),
  useSessionImportActions: () => new Proxy({}, {
    get: (_t, op) => ({ mutate: (v: unknown) => state.calls.push([String(op), v]), isPending: false }),
  }),
}));

import { SessionImports, roleChanges, voicesSummary } from './SessionImports';

function staged(over: Partial<SessionImport> = {}): SessionImport {
  return {
    id: '4', status: 'staged', kind: 'therapy', filename: 'session.md', createdAt: '2026-10-03T10:00:00Z',
    startedAt: null, language: 'en', owner: 'Ann', therapist: 'Counsellor',
    speakers: [
      { label: 'Ann', segments: 3, words: 40, role: 'owner' },
      { label: 'Counsellor', segments: 2, words: 20, role: 'therapist' },
      { label: 'Speaker unsure', segments: 1, words: 1, role: 'unclear' },
    ],
    segments: 6, turns: 5, durationSeconds: 63, leftOut: 2,
    missing: ['the day and time of the session'], alreadyImported: null,
    estimate: { passages: 2, indexingDollars: 0.0001, readingDollars: 0.002,
                text: 'Importing sends the session to OpenAI: about $0.002.' },
    reflectionId: null,
    voices: { status: 'none', report: null, error: null, hasRecording: false, estimate: null },
    ...over,
  };
}

beforeEach(() => { state.items = []; state.calls = []; });

describe('a staged session', () => {
  it('shows the cost and refuses to import before the day and time are given', () => {
    state.items = [staged()];
    render(<SessionImports />);
    expect(screen.getByText('Importing sends the session to OpenAI: about $0.002.')).toBeInTheDocument();
    expect(screen.getByText('Before importing, say the day and time of the session.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import session' })).toBeDisabled();
    expect(screen.getByText(/2 lines before the first turn were left out/)).toBeInTheDocument();
  });

  it('imports on the click once nothing is missing', () => {
    state.items = [staged({ startedAt: '2026-09-30T18:00', missing: [] })];
    render(<SessionImports />);
    fireEvent.click(screen.getByRole('button', { name: 'Import session' }));
    expect(state.calls).toEqual([['commit', '4']]);
  });

  it('sends the day and time the owner enters', () => {
    state.items = [staged()];
    render(<SessionImports />);
    fireEvent.change(screen.getByLabelText('When the session started'), { target: { value: '2026-09-30T18:00' } });
    expect(state.calls).toEqual([['update', { id: '4', changes: { startedAt: '2026-09-30T18:00' } }]]);
  });

  it('refuses a transcript that is already in the journal', () => {
    state.items = [staged({ startedAt: '2026-09-30T18:00', missing: [], alreadyImported: { importId: '2', on: '2026-10-01' } })];
    render(<SessionImports />);
    expect(screen.getByRole('alert')).toHaveTextContent('already in your journal');
    expect(screen.getByRole('button', { name: 'Import session' })).toBeDisabled();
  });
});

describe('who is who', () => {
  const item = staged();

  it('keeps one speaker as you and at most one as the therapist', () => {
    expect(roleChanges(item, 'Counsellor', 'owner')).toEqual({ owner: 'Counsellor', therapist: null });
    expect(roleChanges(item, 'Ann', 'therapist')).toEqual({ therapist: 'Ann', owner: null });
    expect(roleChanges(item, 'Ann', 'unclear')).toEqual({ owner: null });
    expect(roleChanges(item, 'Speaker unsure', 'unclear')).toEqual({});
  });
});

describe('an imported session', () => {
  it('can be taken back out of the journal', () => {
    state.items = [staged({ status: 'imported', startedAt: '2026-09-30T18:00', missing: [], reflectionId: '9' })];
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<SessionImports />);
    expect(screen.getByText(/In your journal/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Undo import' }));
    expect(state.calls[0][0]).toBe('undo');
  });
});

describe('speakers from the recording', () => {
  it('asks for the recording first and says adding it sends nothing', () => {
    state.items = [staged()];
    render(<SessionImports />);
    expect(screen.getByText(/Adding it here sends nothing/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add the recording' })).toBeEnabled();
  });

  it('shows the cost before the click that sends the recording', () => {
    state.items = [staged({ voices: { status: 'none', report: null, error: null, hasRecording: true,
      estimate: { minutes: 60, dollars: 0.36, text: 'Sorting out speakers sends the recording, about $0.36.' } } })];
    render(<SessionImports />);
    expect(screen.getByText('Sorting out speakers sends the recording, about $0.36.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Sort out speakers' }));
    expect(state.calls).toEqual([['startVoices', '4']]);
  });

  it('holds the import while the recording is being listened to', () => {
    state.items = [staged({ startedAt: '2026-09-30T18:00', missing: [],
      voices: { status: 'running', report: null, error: null, hasRecording: true, estimate: null } })];
    render(<SessionImports />);
    expect(screen.getByRole('status')).toHaveTextContent('Listening to the recording');
    expect(screen.getByRole('button', { name: 'Import session' })).toBeDisabled();
  });

  it('says what changed, naming the owner as you', () => {
    expect(voicesSummary({ segments: 9, heard: 9, labelled: 5, agreed: 4, contradicted: 1,
      attributed: { Ann: 2, Counsellor: 1 }, doubtful: 1 }, 'Ann')).toBe(
      'Uncertain lines now have a speaker: 2 lines to you, 1 line to Counsellor. '
      + '1 labelled line the voices disagreed with is now marked unsure. 1 line stays unclear. '
      + 'The voices agreed with 4 of the 5 lines the transcript had labelled.');
  });
});

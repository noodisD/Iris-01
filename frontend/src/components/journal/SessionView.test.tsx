/**
 * A session in the journal: every turn says who spoke, and the owner can see
 * which words count as theirs (ADR-0028). Every line here is invented.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { JournalSession, SessionTurn } from '@/types/api';
import { SessionView, clock } from './SessionView';

const turn = (at: number, label: string, role: SessionTurn['role'], text: string): SessionTurn =>
  ({ at, label, role, text });

const session: JournalSession = {
  kind: 'therapy', startedAt: '2026-09-30T18:00', language: 'en', owner: 'Ann', therapist: 'Counsellor',
  durationSeconds: 3010,
  turns: [
    turn(5, 'Ann', 'owner', 'I kept postponing the call to my landlord.'),
    turn(21, 'Counsellor', 'therapist', 'What happened when you called?'),
    turn(30, 'Ann', 'owner', 'He fixed the heating straight away.'),
    turn(52, 'Speaker unsure', 'unclear', 'Yes.'),
    turn(60, 'Counsellor', 'therapist', 'And how did that feel?'),
    turn(75, 'Ann', 'owner', 'Silly, mostly.'),
    turn(3010, 'Counsellor', 'therapist', 'Let us stop there for today.'),
  ],
};

describe('a session in the journal', () => {
  it('says what it was and which turns count as evidence', () => {
    render(<SessionView session={session} />);
    expect(screen.getByText('Therapy session, at 18:00, about 50 minutes.')).toBeInTheDocument();
    expect(screen.getByText(/Only your turns are read as evidence/)).toBeInTheDocument();
  });

  it('names the speaker of every turn and marks the owner and the unclear ones', () => {
    render(<SessionView session={session} />);
    const turns = within(screen.getByRole('list', { name: 'Turns of the session' })).getAllByRole('listitem');
    expect(turns).toHaveLength(6);
    expect(turns[0]).toHaveTextContent('0:05Ann (you)I kept postponing');
    expect(turns[1]).toHaveTextContent('Counsellor');
    expect(turns[1]).not.toHaveTextContent('(you)');
    expect(turns[3]).toHaveTextContent('Speaker unsure (speaker unclear)');
  });

  it('opens to the whole session on request', () => {
    render(<SessionView session={session} />);
    const more = screen.getByRole('button', { name: 'Show the whole session (7 turns)' });
    expect(more).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(more);
    expect(screen.getByText('Let us stop there for today.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show less' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('writes recording times as a clock', () => {
    expect(clock(5)).toBe('0:05');
    expect(clock(3626)).toBe('1:00:26');
  });
});

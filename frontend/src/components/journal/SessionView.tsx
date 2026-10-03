import React from 'react';
import type { JournalSession, SessionTurn } from '@/types/api';
import { Button } from '@/ui';
import styles from './SessionView.module.css';

/** Turns shown before the owner asks for the rest: an hour of talk would bury the journal. */
const FIRST_TURNS = 6;

export function clock(seconds: number): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours ? `${hours}:${pad(minutes)}:${pad(seconds % 60)}` : `${minutes}:${pad(seconds % 60)}`;
}

function summary(session: JournalSession): string {
  const time = session.startedAt?.split('T')[1];
  const minutes = session.durationSeconds ? Math.round(session.durationSeconds / 60) : null;
  return ['Therapy session', time && `at ${time}`, minutes && `about ${minutes} minutes`]
    .filter(Boolean).join(', ') + '.';
}

const ROLE_NOTE: Record<SessionTurn['role'], string> = {
  owner: ' (you)',
  therapist: '',
  unclear: ' (speaker unclear)',
};

/**
 * A therapy session, turn by turn (ADR-0028). The owner's words are set in full
 * ink because they are the only part that can become evidence; the therapist's
 * turns and the unclear ones sit back as context. Roles come from the server's
 * reading, the same one every engine uses.
 */
export function SessionView({ session }: { session: JournalSession }) {
  const [whole, setWhole] = React.useState(false);
  const listId = React.useId();
  const shown = whole ? session.turns : session.turns.slice(0, FIRST_TURNS);
  return (
    <div className={styles.session}>
      <p className={styles.summary}>{summary(session)}</p>
      <p className={styles.rule}>
        Only your turns are read as evidence. The therapist&rsquo;s turns, and any whose speaker is
        unclear, are kept as context.
      </p>
      <ol id={listId} className={styles.turns} aria-label="Turns of the session">
        {shown.map((turn, index) => (
          <li key={index} className={`${styles.turn} ${styles[turn.role]}`}>
            <span className={styles.at}>{clock(turn.at)}</span>
            <span className={styles.speaker}>{turn.label}{ROLE_NOTE[turn.role]}</span>
            <p className={styles.words}>{turn.text}</p>
          </li>
        ))}
      </ol>
      {session.turns.length > FIRST_TURNS && (
        <div>
          <Button size="sm" aria-controls={listId} aria-expanded={whole} onClick={() => setWhole(open => !open)}>
            {whole ? 'Show less' : `Show the whole session (${session.turns.length} turns)`}
          </Button>
        </div>
      )}
    </div>
  );
}

import React from 'react';
import { useSessionImportActions, useSessionImports } from '@/hooks/useSessionImports';
import type { SessionImportChanges } from '@/api/sessions';
import type { SessionImport, SessionRole, SessionVoicesReport } from '@/types/api';
import { formatEventDate } from '@/lib/dates';
import { Button, ChoiceGroup, Field, Section } from '@/ui';
import styles from './SessionImports.module.css';

const ROLES: { value: SessionRole; label: string }[] = [
  { value: 'owner', label: 'You' },
  { value: 'therapist', label: 'Therapist' },
  { value: 'unclear', label: 'Unclear' },
];

const LANGUAGES: [string, string][] = [
  ['pl', 'Polish'], ['en', 'English'], ['de', 'German'], ['es', 'Spanish'],
  ['fr', 'French'], ['it', 'Italian'], ['uk', 'Ukrainian'],
];

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'That did not work. Try again.';
}

/** What changes when a speaker is given a role: one speaker is you, at most one the therapist. */
export function roleChanges(item: SessionImport, label: string, role: SessionRole): SessionImportChanges {
  if (role === 'owner') return { owner: label, ...(item.therapist === label ? { therapist: null } : {}) };
  if (role === 'therapist') return { therapist: label, ...(item.owner === label ? { owner: null } : {}) };
  return {
    ...(item.owner === label ? { owner: null } : {}),
    ...(item.therapist === label ? { therapist: null } : {}),
  };
}

const AUDIO_ACCEPT = '.m4a,.mp3,.wav,.webm,.ogg,.flac,.aac,.mp4';

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** What the voices pass changed, said as a sentence or two. */
export function voicesSummary(report: SessionVoicesReport, owner: string | null): string {
  if (report.transcribed) {
    const named = Object.entries(report.named ?? {}).filter(([, count]) => count > 0)
      .map(([label, count]) => `${plural(count, 'line', 'lines')} ${label === owner ? 'yours' : `by ${label}`}`);
    return [`Transcribed into ${plural(report.segments, 'line', 'lines')}${named.length ? `: ${named.join(', ')}` : ''}.`,
            report.unclear ? `${plural(report.unclear, 'line', 'lines')} could not be matched to a voice and ${report.unclear === 1 ? 'stays' : 'stay'} unclear.` : '',
            'Check who is who below before importing.'].filter(Boolean).join(' ');
  }
  const attributed = Object.entries(report.attributed).filter(([, count]) => count > 0)
    .map(([label, count]) => `${plural(count, 'line', 'lines')} to ${label === owner ? 'you' : label}`);
  const parts = [
    attributed.length ? `Uncertain lines now have a speaker: ${attributed.join(', ')}.` : 'No uncertain line could be given a speaker.',
    report.contradicted ? `${plural(report.contradicted, 'labelled line', 'labelled lines')} the voices disagreed with ${report.contradicted === 1 ? 'is' : 'are'} now marked unsure.` : '',
    report.doubtful ? `${plural(report.doubtful, 'line stays', 'lines stay')} unclear.` : '',
    report.labelled ? `The voices agreed with ${report.agreed} of the ${report.labelled} lines the transcript had labelled.` : '',
  ];
  return parts.filter(Boolean).join(' ');
}

function Voices({ item, onError }: { item: SessionImport; onError: (message?: string) => void }) {
  const actions = useSessionImportActions();
  const input = React.useRef<HTMLInputElement>(null);
  const voices = item.voices;
  const handlers = { onError: (e: unknown) => onError(message(e)), onSuccess: () => onError(undefined) };
  const uploading = actions.addRecording.isPending;

  let body: React.ReactNode;
  if (voices.status === 'queued' || voices.status === 'running') {
    body = <p className={styles.muted} role="status">
      {item.needsTranscript
        ? 'Transcribing the recording. An hour takes about twenty minutes; you can leave this page.'
        : 'Listening to the recording. This takes a few minutes; you can leave this page.'}
    </p>;
  } else if (voices.status === 'done' && voices.report) {
    body = (
      <>
        <p className={styles.cost} role="status">{voicesSummary(voices.report, item.owner)}</p>
        {!voices.report.transcribed && (
          <div className={styles.row}>
            <Button size="sm" disabled={actions.undoVoices.isPending} onClick={() => actions.undoVoices.mutate(item.id, handlers)}>
              Put the transcript&rsquo;s labels back
            </Button>
          </div>
        )}
      </>
    );
  } else if (!voices.hasRecording) {
    body = (
      <>
        <p className={styles.muted}>
          Turns marked uncertain are kept as context, so your words in them do not count. The recording
          can settle most of them. Adding it here sends nothing; you are shown the cost first.
        </p>
        <div className={styles.row}>
          <Button size="sm" disabled={uploading} onClick={() => input.current?.click()}>
            {uploading ? 'Adding…' : 'Add the recording'}
          </Button>
          <input ref={input} type="file" accept={AUDIO_ACCEPT} hidden aria-label="The session recording"
            onChange={e => {
              const file = e.target.files?.[0];
              if (file) actions.addRecording.mutate({ id: item.id, file }, handlers);
              e.target.value = '';
            }} />
        </div>
      </>
    );
  } else if (item.needsTranscript) {
    body = (
      <>
        {voices.estimate && <p className={styles.cost}>{voices.estimate.text}</p>}
        {voices.status === 'failed' && voices.error && <p role="alert" className={styles.error}>{voices.error}</p>}
        <div className={styles.row}>
          <Button size="sm" variant="primary" disabled={actions.startVoices.isPending}
            onClick={() => actions.startVoices.mutate(item.id, handlers)}>
            Transcribe the recording
          </Button>
        </div>
      </>
    );
  } else {
    const ready = !!item.owner && !!item.therapist;
    body = (
      <>
        {voices.estimate && <p className={styles.cost}>{voices.estimate.text}</p>}
        {voices.status === 'failed' && voices.error && <p role="alert" className={styles.error}>{voices.error}</p>}
        {!ready && <p className={styles.warn}>Mark which speaker is you and which is the therapist first.</p>}
        <div className={styles.row}>
          <Button size="sm" disabled={!ready || actions.startVoices.isPending}
            onClick={() => actions.startVoices.mutate(item.id, handlers)}>
            Sort out speakers
          </Button>
        </div>
      </>
    );
  }
  return (
    <section className={styles.speakers} aria-labelledby={`voices-${item.id}`}>
      <h4 id={`voices-${item.id}`} className={styles.subhead}>{item.needsTranscript ? 'Transcript' : 'Speakers from the recording'}</h4>
      {body}
    </section>
  );
}

function when(item: SessionImport): string {
  if (!item.startedAt) return 'Session with no date yet';
  const [day, time] = item.startedAt.split('T');
  return `Session of ${formatEventDate(day)} at ${time}`;
}

function Staged({ item }: { item: SessionImport }) {
  const actions = useSessionImportActions();
  const [error, setError] = React.useState<string>();
  const handlers = { onError: (e: unknown) => setError(message(e)), onSuccess: () => setError(undefined) };
  const change = (changes: SessionImportChanges) => actions.update.mutate({ id: item.id, changes }, handlers);
  const minutes = item.durationSeconds ? Math.round(item.durationSeconds / 60) : null;
  const blocked = item.missing.length > 0 || !!item.alreadyImported;

  return (
    <article className={styles.card} aria-label={item.filename ?? 'Session transcript'}>
      <header className={styles.head}>
        <h3 className={styles.title}>{item.filename ?? 'Session transcript'}</h3>
        <p className={styles.muted}>
          {item.needsTranscript
            ? `A recording${item.voices.estimate ? ` of about ${item.voices.estimate.minutes} minutes` : ''}, not transcribed yet. Set the language before transcribing.`
            : `${item.turns} turns${minutes ? `, about ${minutes} minutes` : ''}.`}
          {item.leftOut > 0 && ` ${item.leftOut} line${item.leftOut === 1 ? '' : 's'} before the first turn ${item.leftOut === 1 ? 'was' : 'were'} left out.`}
        </p>
      </header>

      <div className={styles.fields}>
        <Field label="When the session started">
          <input type="datetime-local" value={item.startedAt ?? ''}
            onChange={e => { if (e.target.value) change({ startedAt: e.target.value }); }} />
        </Field>
        <Field label="Language of the transcript">
          <select value={item.language ?? ''} onChange={e => change({ language: e.target.value })}>
            {!LANGUAGES.some(([code]) => code === item.language) && item.language &&
              <option value={item.language}>{item.language}</option>}
            {LANGUAGES.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
          </select>
        </Field>
      </div>

      {!item.needsTranscript && <section className={styles.speakers} aria-labelledby={`who-${item.id}`}>
        <h4 id={`who-${item.id}`} className={styles.subhead}>Who is who</h4>
        <p className={styles.muted}>
          Only turns by the speaker marked as you can become evidence. The therapist&rsquo;s turns,
          and unclear ones, are kept as context: IRIS reads them with their speaker and never
          quotes them as yours.
        </p>
        <ul className={styles.speakerList}>
          {item.speakers.map(speaker => (
            <li key={speaker.label} className={styles.speaker}>
              <span className={styles.label}>{speaker.label}</span>
              <span className={styles.words}>{speaker.words} words</span>
              <ChoiceGroup label={`Who ${speaker.label} is`} options={ROLES} value={speaker.role}
                disabled={actions.update.isPending}
                onChange={role => { if (role) change(roleChanges(item, speaker.label, role)); }} />
            </li>
          ))}
        </ul>
      </section>}

      <Voices item={item} onError={setError} />

      {item.alreadyImported && (
        <p role="alert" className={styles.warn}>
          This transcript is already in your journal (imported {formatEventDate(item.alreadyImported.on)}).
        </p>
      )}
      {item.estimate && <p className={styles.cost}>{item.estimate.text}</p>}
      {item.missing.length > 0 && <p className={styles.warn}>Before importing, say {item.missing.join(' and ')}.</p>}
      {error && <p role="alert" className={styles.error}>{error}</p>}

      <div className={styles.row}>
        <Button variant="primary"
          disabled={blocked || actions.commit.isPending || item.voices.status === 'queued' || item.voices.status === 'running'}
          onClick={() => actions.commit.mutate(item.id, handlers)}>
          {actions.commit.isPending ? 'Importing…' : 'Import session'}
        </Button>
        <Button variant="quiet" disabled={actions.discard.isPending}
          onClick={() => actions.discard.mutate(item.id, handlers)}>
          Discard
        </Button>
      </div>
    </article>
  );
}

function Imported({ item }: { item: SessionImport }) {
  const actions = useSessionImportActions();
  const [error, setError] = React.useState<string>();
  return (
    <li className={styles.imported}>
      <span className={styles.importedText}>
        <span className={styles.label}>{when(item)}</span>
        <span className={styles.muted}>
          {item.status === 'importing' ? 'Being imported…' : 'In your journal. IRIS reads your turns in the background.'}
        </span>
      </span>
      {item.status === 'imported' && (
        <Button size="sm" variant="danger" disabled={actions.undo.isPending}
          onClick={() => {
            if (confirm('Take this session out of your journal? It goes back to waiting here, so you can fix it and import it again.')) {
              actions.undo.mutate(item.id, { onError: e => setError(message(e)) });
            }
          }}>
          Undo import
        </Button>
      )}
      {error && <p role="alert" className={styles.error}>{error}</p>}
    </li>
  );
}

/** Sessions waiting for the owner's check, and the ones imported recently (ADR-0028). */
export function SessionImports() {
  const { data } = useSessionImports();
  const staged = (data ?? []).filter(item => item.status === 'staged');
  const imported = (data ?? []).filter(item => item.status === 'imported' || item.status === 'importing');
  if (!staged.length && !imported.length) return null;
  return (
    <Section title="Therapy sessions">
      <div className={styles.list}>
        {staged.map(item => <Staged key={item.id} item={item} />)}
        {imported.length > 0 && (
          <ul className={styles.importedList}>
            {imported.map(item => <Imported key={item.id} item={item} />)}
          </ul>
        )}
      </div>
    </Section>
  );
}

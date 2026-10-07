import React from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import * as importApi from '@/api/importing';
import {
  isBusy, useImportActions, useImportAdapters, useImportBatch, useImportBatches, useImportEntries,
} from '@/hooks/useImport';
import { LoadingState, ErrorState } from '@/components/states';
import { AudioRecorder } from '@/components/AudioRecorder';
import { SessionImports } from '@/components/SessionImports';
import { uploadSessionAudio, uploadSessionTranscript } from '@/api/sessions';
import type { ImportBatch, ImportEntry } from '@/types/api';
import { Badge, Button, Page, Section } from '@/ui';
import styles from './ImportScreen.module.css';

const TEXT_ACCEPT = '.zip,.md,.markdown,.txt,.json,.csv';
const AUDIO_ACCEPT = '.m4a,.mp3,.wav,.webm,.ogg,.flac,.aac,.mp4';
const SESSION_ACCEPT = `.md,.markdown,.txt,${AUDIO_ACCEPT}`;

const badgeTone: Record<string, 'neutral' | 'confirmed' | 'worse' | 'action'> = {
  staged: 'neutral',
  excluded: 'neutral',
  duplicate: 'action',
  imported: 'confirmed',
  failed: 'worse',
};

function DropZone({
  label, hint, accept, onFiles, busy,
}: {
  label: string; hint: string; accept: string;
  onFiles: (files: FileList) => void; busy: boolean;
}) {
  const input = React.useRef<HTMLInputElement>(null);
  const [over, setOver] = React.useState(false);

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (e.dataTransfer.files?.length) onFiles(e.dataTransfer.files);
      }}
      className={[styles.drop, over ? styles.over : '', busy ? styles.busy : ''].filter(Boolean).join(' ')}
    >
      <h2 className={styles.dropTitle}>{label}</h2>
      <p className={styles.dropHint}>{hint}</p>
      <div>
        <Button disabled={busy} onClick={() => input.current?.click()}>Choose files</Button>
        <span className={styles.dropOr}>or drop them here</span>
      </div>
      <input
        ref={input} type="file" accept={accept} multiple hidden aria-label={label}
        onChange={(e) => { if (e.target.files?.length) onFiles(e.target.files); e.target.value = ''; }}
      />
    </div>
  );
}

function ProgressBar({ fraction, label }: { fraction: number; label: string }) {
  return (
    <div className={styles.progress}>
      <span className={styles.progressLabel}>{label}</span>
      <progress className={styles.bar} value={Math.round(fraction * 100)} max={100} aria-label={label} />
    </div>
  );
}

function EntryRow({
  entry, onDate, onToggle, onFileDate,
}: {
  entry: ImportEntry;
  onDate: (id: string, value: string) => void;
  onToggle: (entry: ImportEntry) => void;
  onFileDate: (id: string) => void;
}) {
  const undated = entry.occurredOn === null;
  const excluded = entry.status === 'excluded';
  // An entry that failed to import is waiting to be tried again, so its button
  // offers that. It used to offer "exclude", which is the opposite of what
  // someone looking at a failure wants.
  const retryable = entry.status === 'failed';
  // Marked for "you must fix this", and for "we guessed, check it".
  const dateState = undated ? styles.dateMissing : entry.dateConfidence === 'probable' ? styles.dateGuess : '';

  return (
    <li className={`${styles.entry} ${excluded ? styles.excluded : ''}`}>
      <input
        type="date" aria-label={`Date of ${entry.sourceName}`}
        value={entry.occurredOn ?? ''}
        onChange={(e) => e.target.value && onDate(entry.id, e.target.value)}
        className={`${styles.date} ${dateState}`}
      />
      <div className={styles.entryText}>
        <span className={styles.excerpt}>
          {entry.excerpt || (entry.hasAudio ? 'Waiting for the transcript…' : '(empty)')}
        </span>
        <span className={styles.source}>
          {entry.sourceName}
          {entry.hasAudio && ', a recording'}
        </span>
        {entry.dateSource === 'mtime' && (
          <span className={styles.guess}>Dated by when its file was last saved, which is a guess</span>
        )}
        {undated && entry.fileModifiedOn && !excluded && (
          <Button variant="quiet" size="sm" className={styles.inlineAction} onClick={() => onFileDate(entry.id)}>
            File last saved {entry.fileModifiedOn}. Use that?
          </Button>
        )}
        {entry.warnings.map((w, i) => <span key={i} className={styles.guess}>{w}</span>)}
        {entry.error && <span className={styles.failed}>{entry.error}</span>}
      </div>
      <Badge tone={badgeTone[entry.status] ?? 'neutral'}>{entry.status}</Badge>
      <Button
        variant="quiet" size="sm"
        aria-label={retryable ? 'try this entry again'
                    : excluded ? 'include this entry' : 'exclude this entry'}
        onClick={() => onToggle(entry)}
      >
        {retryable ? 'Retry' : excluded ? 'Include' : 'Exclude'}
      </Button>
    </li>
  );
}

export function Review({ batch, onDone }: { batch: ImportBatch; onDone: () => void }) {
  const live = batch.kind === 'audio';
  const { data: entries, isLoading } = useImportEntries(batch.id, live);
  const { data: adapters } = useImportAdapters();
  const actions = useImportActions(batch.id);
  const [bulkDate, setBulkDate] = React.useState('');

  const counts = batch.counts;
  const waiting = counts.awaitingTranscript > 0;
  const blocked = counts.needsDate > 0 || waiting;
  // An entry whose absence of a date the owner has already accepted is settled,
  // so it is not one of the blockers this bar is about.
  const undatedIds = (entries ?? [])
    .filter((e) => e.occurredOn === null && !e.dateUnknownAccepted && e.status === 'staged')
    .map((e) => e.id);
  const fileDatable = (entries ?? [])
    .filter((e) => e.occurredOn === null && e.status === 'staged' && e.fileModifiedOn)
    .map((e) => e.id);

  return (
    <section className={styles.review} aria-label="Review the import">
      {batch.status === 'failed' && (
        <div role="alert" className={styles.notice}>
          <strong>{counts.imported} of {counts.total} entries were imported; {counts.failed} failed.</strong>
          <span className={styles.muted}>
            The ones that landed are safe and are not here. Put the rest right below and
            import again, or discard what is left.
          </span>
          {batch.error && <span className={styles.muted}>{batch.error}</span>}
        </div>
      )}

      <div className={styles.reviewHead}>
        <label className={styles.readAs}>
          <span className={styles.label}>Read as</span>
          <select
            value={batch.adapter ?? ''}
            onChange={(e) => actions.reparse.mutate(e.target.value)}
            disabled={actions.reparse.isPending}
          >
            {(adapters ?? []).map((a) => (
              <option key={a.name} value={a.name}>{a.label}</option>
            ))}
          </select>
          <span className={styles.muted}>{actions.reparse.isPending ? 'Re-reading…' : 'Change this if the entries look wrong.'}</span>
        </label>
        <Button variant="danger" size="sm" onClick={() => actions.discard.mutate(false, { onSuccess: onDone })}>
          Discard this import
        </Button>
      </div>

      <ul className={styles.counts}>
        <li>{counts.total} entries</li>
        {counts.needsDate > 0 && <li className={styles.failed}>{counts.needsDate} need a date</li>}
        {counts.duplicate > 0 && <li>{counts.duplicate} already imported</li>}
        {counts.excluded > 0 && <li>{counts.excluded} excluded</li>}
        {counts.earliest && <li>From {counts.earliest} to {counts.latest}</li>}
      </ul>

      {fileDatable.length > 0 && (
        <div className={`${styles.notice} ${styles.row}`}>
          <span className={styles.noticeText}>
            {fileDatable.length} undated {fileDatable.length === 1 ? 'entry' : 'entries'} can
            be dated by when {fileDatable.length === 1 ? 'its file was' : 'their files were'} last
            saved. That is a guess (a note is often edited after the day it describes),
            so those dates stay marked for you to check.
          </span>
          <Button disabled={actions.bulk.isPending}
                  onClick={() => actions.bulk.mutate({ ids: fileDatable, op: 'use_file_date' })}>
            Use file dates
          </Button>
        </div>
      )}
      {undatedIds.length > 0 && (
        <div className={`${styles.notice} ${styles.urgent} ${styles.row}`}>
          <span className={styles.noticeText}>
            {undatedIds.length} {undatedIds.length === 1 ? 'entry has' : 'entries have'} no date
            IRIS could read. It will not guess one: an entry filed on the wrong
            day is counted in the wrong week for good.
          </span>
          <input type="date" aria-label="Date for all undated entries" value={bulkDate}
                 onChange={(e) => setBulkDate(e.target.value)} />
          <Button disabled={!bulkDate}
                  onClick={() => actions.bulk.mutate({ ids: undatedIds, op: 'set_date', occurredOn: bulkDate })}>
            Set all
          </Button>
          {/* The third answer, which the screen never offered: the day is
              not recoverable, and saying so is not the same as guessing. The
              service has accepted it since the undated work landed; without
              this button an archive of undated recordings could only be
              excluded or abandoned. */}
          <Button onClick={() => actions.bulk.mutate({ ids: undatedIds, op: 'accept_unknown_date' })}>
            Accept as undated
          </Button>
          <Button variant="quiet" onClick={() => actions.bulk.mutate({ ids: undatedIds, op: 'exclude' })}>
            Exclude all
          </Button>
        </div>
      )}

      {isLoading ? <LoadingState label="Iris is reading your entries…" /> : (
        <ul className={styles.entries} aria-label="Entries found">
          {(entries ?? []).map((e) => (
            <EntryRow
              key={e.id} entry={e}
              onDate={(id, occurredOn) => actions.setDate.mutate({ id, occurredOn })}
              onFileDate={(id) => actions.bulk.mutate({ ids: [id], op: 'use_file_date' })}
              onToggle={(entry) => actions.setStatus.mutate({
                id: entry.id,
                status: entry.status === 'excluded' || entry.status === 'failed'
                  ? 'staged' : 'excluded',
              })}
            />
          ))}
        </ul>
      )}

      <div className={styles.row}>
        <Button
          variant="primary"
          disabled={blocked || actions.commit.isPending || counts.staged === 0}
          onClick={() => actions.commit.mutate()}
        >
          {actions.commit.isPending ? 'Importing…' : `Import ${counts.staged} entries`}
        </Button>
        {counts.needsDate > 0 && <span className={styles.failed}>Set or exclude the undated entries first.</span>}
        {counts.needsDate === 0 && waiting && (
          <span className={styles.muted}>{counts.awaitingTranscript} recording(s) still being transcribed…</span>
        )}
      </div>
    </section>
  );
}

function Finished({ batch, onDone }: { batch: ImportBatch; onDone: () => void }) {
  const actions = useImportActions(batch.id);
  return (
    <section className={styles.finished} aria-label="Import finished">
      <h2 className={styles.finishedTitle}>{batch.committedCount} entries added to your journal.</h2>
      <p className={styles.muted}>
        Iris is still reading them. Embedding and pattern-finding happen in the
        background, so themes may take a few minutes to appear, and a large
        import can reorganise the ones you already have.
      </p>
      <div className={styles.row}>
        <Button onClick={onDone}>Import something else</Button>
        <Button
          variant="danger"
          disabled={actions.discard.isPending}
          onClick={() => {
            // Undo exists because the dates are the point: if an export was read
            // with the wrong format, living with four hundred misdated entries
            // is not an acceptable answer.
            if (confirm(`Remove all ${batch.committedCount} entries this import created?`)) {
              actions.discard.mutate(true, { onSuccess: onDone });
            }
          }}
        >
          Undo this import
        </Button>
      </div>
    </section>
  );
}

export function ImportScreen() {
  const qc = useQueryClient();
  const [activeId, setActiveId] = React.useState<string>();
  const [progress, setProgress] = React.useState<{ label: string; fraction: number }>();
  const [error, setError] = React.useState<string>();

  const { data: batch } = useImportBatch(activeId);
  const { data: batches, isLoading, isError, refetch } = useImportBatches();

  const send = async (files: FileList, kind: 'text' | 'audio') => {
    setError(undefined);
    try {
      let batchId: string | undefined;
      const list = Array.from(files);
      for (const [i, file] of list.entries()) {
        const label = list.length > 1 ? `uploading ${i + 1} of ${list.length}` : 'uploading';
        setProgress({ label, fraction: 0 });
        if (kind === 'text') {
          const created = await importApi.uploadExport(file, {
            onProgress: (fraction) => setProgress({ label, fraction }),
          });
          batchId = created.id;
        } else {
          const staged = await importApi.uploadRecording(file, {
            filename: file.name,
            capturedSource: 'upload',
            batchId,
            onProgress: (fraction) => setProgress({ label, fraction }),
          });
          batchId = staged.batchId;
        }
      }
      setActiveId(batchId);
      qc.invalidateQueries({ queryKey: qk.importBatches });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The upload failed.');
    } finally {
      setProgress(undefined);
    }
  };

  /** A session transcript is staged and waits for the owner; nothing is sent (ADR-0028). */
  const sendSession = async (files: FileList) => {
    setError(undefined);
    try {
      for (const file of Array.from(files)) {
        setProgress({ label: 'uploading', fraction: 0 });
        const onProgress = (fraction: number) => setProgress({ label: 'uploading', fraction });
        const audio = AUDIO_ACCEPT.split(',').some(ext => file.name.toLowerCase().endsWith(ext));
        await (audio ? uploadSessionAudio(file, { onProgress }) : uploadSessionTranscript(file, { onProgress }));
      }
      qc.invalidateQueries({ queryKey: qk.sessionImports });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The upload failed.');
    } finally {
      setProgress(undefined);
    }
  };

  /** A recording made here takes the same path as an uploaded one, and carries
   *  its own timestamp — so unlike an upload, it already knows its date. */
  const saveRecording = async (blob: Blob, filename: string, recordedAt: string) => {
    const staged = await importApi.uploadRecording(blob, {
      filename, recordedAt, capturedSource: 'recording',
      onProgress: (fraction) => setProgress({ label: 'saving recording', fraction }),
    });
    setProgress(undefined);
    setActiveId(staged.batchId);
    qc.invalidateQueries({ queryKey: qk.importBatches });
  };

  const done = () => { setActiveId(undefined); qc.invalidateQueries({ queryKey: qk.importBatches }); };

  if (isLoading) return <LoadingState label="Iris is checking what you have brought…" />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;

  return (
    <Page title="Import"
      description="Bring in what you have already written or recorded. Nothing is saved until you have checked what IRIS found, and every entry keeps the day you wrote it.">
      {error && <ErrorState message={error} onRetry={() => setError(undefined)} />}
      {progress && <ProgressBar fraction={progress.fraction} label={progress.label} />}

      {batch && isBusy(batch) && (
        <LoadingState label={
          batch.status === 'parsing'
            ? 'Iris is reading your export…'
            : 'Iris is adding your entries…'
        } />
      )}

      {batch && batch.status === 'needs_review' && <Review batch={batch} onDone={done} />}
      {batch && batch.status === 'committed' && <Finished batch={batch} onDone={done} />}
      {/* A batch that got as far as entries and then had some of them fail is
          not an export that could not be read: part of it landed, and the rest
          can be put right here. It used to show one error and a button that
          navigated away, so the only route back was importing the file again —
          which would have duplicated everything that did land. */}
      {batch && batch.status === 'failed' && batch.counts.total > 0 && (
        <Review batch={batch} onDone={done} />
      )}
      {batch && batch.status === 'failed' && batch.counts.total === 0 && (
        <ErrorState message={batch.error ?? 'That export could not be read.'} onRetry={done} />
      )}

      {!batch && (
        <>
          <div className={styles.drops}>
            <DropZone
              label="Written journals" accept={TEXT_ACCEPT} busy={!!progress}
              hint="An export from Notion, Obsidian or Day One: a zip, a folder of notes, or one long file."
              onFiles={(f) => send(f, 'text')}
            />
            <div className={styles.voice}>
              <DropZone
                label="Voice journals" accept={AUDIO_ACCEPT} busy={!!progress}
                hint="Recordings from your phone. They are sent to OpenAI to be transcribed; the audio stays here so you can listen back."
                onFiles={(f) => send(f, 'audio')}
              />
              <AudioRecorder disabled={!!progress} onSave={saveRecording} />
            </div>
            <DropZone
              label="Therapy sessions" accept={SESSION_ACCEPT} busy={!!progress}
              hint="The recording, or a transcript with each turn marked by time and speaker. It waits here until you have said when it was and which speaker is you; nothing is sent before you ask."
              onFiles={sendSession}
            />
          </div>

          <SessionImports />

          {(batches ?? []).length === 0 ? (
            <p className={styles.muted}>Nothing imported yet. Whatever you have written elsewhere can come in here, dated when you wrote it.</p>
          ) : (
            <Section title="Previous imports">
              <ul className={styles.previous}>
                {(batches ?? []).map((b) => (
                  <li key={b.id}>
                    <button type="button" className={styles.previousItem} onClick={() => setActiveId(b.id)}>
                      <span className={styles.previousName}>{b.originalFilename ?? 'Recording'}</span>
                      <span className={styles.muted}>
                        {b.status === 'committed' ? `${b.committedCount} imported` : b.status},{' '}
                        {new Date(b.createdAt).toLocaleDateString()}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </>
      )}
    </Page>
  );
}

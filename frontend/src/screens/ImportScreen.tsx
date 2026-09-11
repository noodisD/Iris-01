import React from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import * as importApi from '@/api/importing';
import {
  isBusy, useImportActions, useImportAdapters, useImportBatch, useImportBatches, useImportEntries,
} from '@/hooks/useImport';
import { LoadingState, ErrorState, EmptyState } from '@/components/states';
import { AudioRecorder } from '@/components/AudioRecorder';
import type { ImportBatch, ImportEntry } from '@/types/api';

const TEXT_ACCEPT = '.zip,.md,.markdown,.txt,.json,.csv';
const AUDIO_ACCEPT = '.m4a,.mp3,.wav,.webm,.ogg,.flac,.aac,.mp4';

const badgeColour: Record<string, string> = {
  staged: 'var(--ink-3)',
  excluded: 'var(--ink-4)',
  duplicate: 'var(--amber)',
  imported: 'var(--sage)',
  failed: 'var(--rose)',
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
      onClick={() => !busy && input.current?.click()}
      style={{
        border: `1px dashed ${over ? 'var(--sage)' : 'var(--line)'}`,
        background: over ? 'rgba(169,200,163,0.06)' : 'var(--bg-2)',
        borderRadius: 10, padding: '28px 22px', cursor: busy ? 'wait' : 'pointer',
        opacity: busy ? 0.6 : 1, transition: 'border-color 0.15s, background 0.15s',
      }}
    >
      <div className="kicker" style={{ marginBottom: 8 }}>{label}</div>
      <div className="serif ital" style={{ fontSize: 16, color: 'var(--ink-2)', lineHeight: 1.4 }}>
        {hint}
      </div>
      <input
        ref={input} type="file" accept={accept} multiple hidden
        onChange={(e) => { if (e.target.files?.length) onFiles(e.target.files); e.target.value = ''; }}
      />
    </div>
  );
}

function ProgressBar({ fraction, label }: { fraction: number; label: string }) {
  return (
    <div className="col" style={{ gap: 6 }}>
      <div className="kicker">{label}</div>
      <div style={{ height: 3, background: 'var(--line-soft)', borderRadius: 2 }}>
        <div style={{
          width: `${Math.round(fraction * 100)}%`, height: '100%',
          background: 'var(--sage)', borderRadius: 2, transition: 'width 0.2s',
        }} />
      </div>
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
  // Red for "you must fix this", amber for "we guessed, check it".
  const dateColour = undated ? 'var(--rose)'
    : entry.dateConfidence === 'probable' ? 'var(--amber)' : 'var(--line-soft)';

  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '140px 1fr 90px 28px', gap: 14,
      alignItems: 'center', padding: '9px 0', borderTop: '1px solid var(--line-soft)',
      opacity: excluded ? 0.4 : 1,
    }}>
      <input
        type="date"
        value={entry.occurredOn ?? ''}
        onChange={(e) => e.target.value && onDate(entry.id, e.target.value)}
        style={{
          background: 'var(--bg-2)', color: 'var(--ink)', fontFamily: 'var(--mono)',
          fontSize: 11, padding: '5px 7px', borderRadius: 5,
          border: `1px solid ${dateColour}`,
        }}
      />
      <div className="col" style={{ gap: 2, minWidth: 0 }}>
        <span style={{
          fontSize: 13, color: 'var(--ink-2)', overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {entry.excerpt || (entry.hasAudio ? 'Waiting for the transcript…' : '(empty)')}
        </span>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--ink-4)' }}>
          {entry.sourceName}
          {entry.hasAudio && ' · recording'}
        </span>
        {entry.dateSource === 'mtime' && (
          <span style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--amber)' }}>
            dated by when its file was last saved · a guess
          </span>
        )}
        {undated && entry.fileModifiedOn && !excluded && (
          <button className="btn ghost" onClick={() => onFileDate(entry.id)}
                  style={{ alignSelf: 'flex-start', fontSize: 10.5, padding: 0, color: 'var(--amber)' }}>
            file last saved {entry.fileModifiedOn}. Use that?
          </button>
        )}
        {entry.warnings.map((w, i) => (
          <span key={i} style={{ fontSize: 10.5, color: 'var(--amber)', fontStyle: 'italic' }}>
            {w}
          </span>
        ))}
        {entry.error && (
          <span style={{ fontSize: 10.5, color: 'var(--rose)' }}>{entry.error}</span>
        )}
      </div>
      <span style={{
        fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.08em',
        textTransform: 'uppercase', color: badgeColour[entry.status] ?? 'var(--ink-3)',
      }}>
        {entry.status}
      </span>
      <button
        className="btn ghost"
        aria-label={excluded ? 'include this entry' : 'exclude this entry'}
        onClick={() => onToggle(entry)}
        style={{ fontSize: 13, color: excluded ? 'var(--sage)' : 'var(--ink-4)' }}
      >
        {excluded ? '+' : '×'}
      </button>
    </div>
  );
}

function Review({ batch, onDone }: { batch: ImportBatch; onDone: () => void }) {
  const live = batch.kind === 'audio';
  const { data: entries, isLoading } = useImportEntries(batch.id, live);
  const { data: adapters } = useImportAdapters();
  const actions = useImportActions(batch.id);
  const [bulkDate, setBulkDate] = React.useState('');

  const counts = batch.counts;
  const waiting = counts.awaitingTranscript > 0;
  const blocked = counts.needsDate > 0 || waiting;
  const undatedIds = (entries ?? []).filter((e) => e.occurredOn === null && e.status === 'staged')
    .map((e) => e.id);
  const fileDatable = (entries ?? [])
    .filter((e) => e.occurredOn === null && e.status === 'staged' && e.fileModifiedOn)
    .map((e) => e.id);

  return (
    <section className="col" style={{ gap: 16 }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div className="col" style={{ gap: 4 }}>
          <div className="kicker">read as</div>
          <div className="row" style={{ gap: 8, alignItems: 'center' }}>
            <select
              value={batch.adapter ?? ''}
              onChange={(e) => actions.reparse.mutate(e.target.value)}
              disabled={actions.reparse.isPending}
              style={{
                background: 'var(--bg-2)', color: 'var(--ink)', border: '1px solid var(--line)',
                borderRadius: 6, padding: '6px 9px', fontSize: 12.5,
              }}
            >
              {(adapters ?? []).map((a) => (
                <option key={a.name} value={a.name}>{a.label}</option>
              ))}
            </select>
            <span style={{ fontSize: 11, color: 'var(--ink-4)', fontStyle: 'italic' }}>
              {actions.reparse.isPending ? 're-reading…' : 'change if this looks wrong'}
            </span>
          </div>
        </div>
        <button className="btn ghost" onClick={() => actions.discard.mutate(false, { onSuccess: onDone })}
                style={{ fontSize: 11, color: 'var(--ink-4)' }}>
          discard this import
        </button>
      </div>

      <div className="row" style={{ gap: 20, flexWrap: 'wrap', fontFamily: 'var(--mono)', fontSize: 11 }}>
        <span style={{ color: 'var(--ink-2)' }}>{counts.total} entries</span>
        {counts.needsDate > 0 && (
          <span style={{ color: 'var(--rose)' }}>{counts.needsDate} need a date</span>
        )}
        {counts.duplicate > 0 && (
          <span style={{ color: 'var(--amber)' }}>{counts.duplicate} already imported</span>
        )}
        {counts.excluded > 0 && <span style={{ color: 'var(--ink-4)' }}>{counts.excluded} excluded</span>}
        {counts.earliest && (
          <span style={{ color: 'var(--ink-3)' }}>{counts.earliest} → {counts.latest}</span>
        )}
      </div>

      {fileDatable.length > 0 && (
        <div className="row" style={{
          gap: 10, alignItems: 'center', padding: '11px 14px',
          border: '1px solid var(--amber)', borderRadius: 8,
        }}>
          <span style={{ fontSize: 12.5, color: 'var(--ink-2)', flex: 1 }}>
            {fileDatable.length} undated {fileDatable.length === 1 ? 'entry' : 'entries'} can
            be dated by when {fileDatable.length === 1 ? 'its file was' : 'their files were'} last
            saved. That is a guess (a note is often edited after the day it describes),
            so those dates stay amber for you to check.
          </span>
          <button className="btn" disabled={actions.bulk.isPending}
                  onClick={() => actions.bulk.mutate({ ids: fileDatable, op: 'use_file_date' })}>
            use file dates
          </button>
        </div>
      )}
      {undatedIds.length > 0 && (
        <div className="row" style={{
          gap: 10, alignItems: 'center', padding: '11px 14px',
          border: '1px solid var(--rose)', borderRadius: 8, background: 'rgba(212,138,138,0.06)',
        }}>
          <span style={{ fontSize: 12.5, color: 'var(--ink-2)', flex: 1 }}>
            {undatedIds.length} {undatedIds.length === 1 ? 'entry has' : 'entries have'} no date
            IRIS could read. It will not guess one — an entry filed on the wrong
            day is counted in the wrong week for good.
          </span>
          <input type="date" value={bulkDate} onChange={(e) => setBulkDate(e.target.value)}
                 style={{
                   background: 'var(--bg-2)', color: 'var(--ink)', fontFamily: 'var(--mono)',
                   fontSize: 11, padding: '5px 7px', borderRadius: 5, border: '1px solid var(--line)',
                 }} />
          <button className="btn" disabled={!bulkDate}
                  onClick={() => actions.bulk.mutate({ ids: undatedIds, op: 'set_date', occurredOn: bulkDate })}
                  style={{ fontSize: 11 }}>
            set all
          </button>
          <button className="btn ghost" style={{ fontSize: 11 }}
                  onClick={() => actions.bulk.mutate({ ids: undatedIds, op: 'exclude' })}>
            exclude all
          </button>
        </div>
      )}

      {isLoading ? <LoadingState label="Iris is reading your entries…" /> : (
        <div className="col" style={{ maxHeight: 460, overflowY: 'auto' }}>
          {(entries ?? []).map((e) => (
            <EntryRow
              key={e.id} entry={e}
              onDate={(id, occurredOn) => actions.setDate.mutate({ id, occurredOn })}
              onFileDate={(id) => actions.bulk.mutate({ ids: [id], op: 'use_file_date' })}
              onToggle={(entry) => actions.setStatus.mutate({
                id: entry.id, status: entry.status === 'excluded' ? 'staged' : 'excluded',
              })}
            />
          ))}
        </div>
      )}

      <div className="row" style={{ gap: 12, alignItems: 'center' }}>
        <button
          className="btn primary"
          disabled={blocked || actions.commit.isPending || counts.staged === 0}
          onClick={() => actions.commit.mutate()}
          style={{ opacity: blocked || counts.staged === 0 ? 0.45 : 1 }}
        >
          {actions.commit.isPending ? 'importing…' : `Import ${counts.staged} entries`}
        </button>
        {counts.needsDate > 0 && (
          <span style={{ fontSize: 11.5, color: 'var(--rose)', fontStyle: 'italic' }}>
            Set or exclude the undated entries first.
          </span>
        )}
        {counts.needsDate === 0 && waiting && (
          <span style={{ fontSize: 11.5, color: 'var(--ink-3)', fontStyle: 'italic' }}>
            {counts.awaitingTranscript} recording(s) still being transcribed…
          </span>
        )}
      </div>
    </section>
  );
}

function Finished({ batch, onDone }: { batch: ImportBatch; onDone: () => void }) {
  const actions = useImportActions(batch.id);
  return (
    <section className="col" style={{ gap: 12 }}>
      <div className="serif" style={{ fontSize: 22, color: 'var(--ink)' }}>
        {batch.committedCount} entries added to your journal.
      </div>
      <p style={{ fontSize: 13, color: 'var(--ink-3)', margin: 0, lineHeight: 1.5, maxWidth: 560 }}>
        Iris is still reading them. Embedding and pattern-finding happen in the
        background, so themes may take a few minutes to appear — and a large
        import can reorganise the ones you already have.
      </p>
      <div className="row" style={{ gap: 10 }}>
        <button className="btn" onClick={onDone}>Import something else</button>
        <button
          className="btn ghost" style={{ fontSize: 11, color: 'var(--rose)' }}
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
          undo this import
        </button>
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
    <div className="col" style={{ padding: '32px 56px 48px', gap: 26 }}>
      <header className="col" style={{ gap: 6, borderBottom: '1px solid var(--line)', paddingBottom: 18 }}>
        <div className="kicker">import · what you have already written</div>
        <h1 className="serif" style={{ margin: 0, fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
          Everything before<br />
          <span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>this.</span>
        </h1>
      </header>

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
      {batch && batch.status === 'failed' && (
        <ErrorState message={batch.error ?? 'That export could not be read.'} onRetry={done} />
      )}

      {!batch && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
            <DropZone
              label="written journals" accept={TEXT_ACCEPT} busy={!!progress}
              hint="An export from Notion, Obsidian, Day One — a zip, a folder of notes, or one long file. Iris will show you what it found before anything is saved."
              onFiles={(f) => send(f, 'text')}
            />
            <div className="col" style={{ gap: 12 }}>
              <DropZone
                label="voice journals" accept={AUDIO_ACCEPT} busy={!!progress}
                hint="Recordings from your phone. They are sent to OpenAI to be transcribed; the audio itself is kept here so you can listen back."
                onFiles={(f) => send(f, 'audio')}
              />
              <AudioRecorder disabled={!!progress} onSave={saveRecording} />
            </div>
          </div>

          {(batches ?? []).length === 0 ? (
            <EmptyState
              title="Nothing imported yet"
              body="Whatever you have written elsewhere can come in here, dated when you wrote it."
            />
          ) : (
            <section className="col" style={{ gap: 2 }}>
              <div className="kicker" style={{ marginBottom: 8 }}>previous imports</div>
              {(batches ?? []).map((b) => (
                <button
                  key={b.id} className="row" onClick={() => setActiveId(b.id)}
                  style={{
                    justifyContent: 'space-between', alignItems: 'baseline', gap: 16,
                    padding: '11px 0', borderTop: '1px solid var(--line-soft)',
                    background: 'none', border: 'none', borderTopStyle: 'solid',
                    cursor: 'pointer', textAlign: 'left', width: '100%',
                  }}
                >
                  <span style={{ fontSize: 13, color: 'var(--ink-2)' }}>
                    {b.originalFilename ?? 'recording'}
                  </span>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)' }}>
                    {b.status === 'committed' ? `${b.committedCount} imported` : b.status}
                    {' · '}{new Date(b.createdAt).toLocaleDateString()}
                  </span>
                </button>
              ))}
            </section>
          )}
        </>
      )}
    </div>
  );
}

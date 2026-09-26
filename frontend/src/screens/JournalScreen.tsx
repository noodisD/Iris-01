import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { useJournal } from '@/hooks/useData';
import { createEntry } from '@/api/journal';
import { LoadingState, ErrorState } from '@/components/states';
import { useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import { formatEventDate } from '@/lib/dates';
import { CheckinPicker, emptyCheckin } from '@/components/journal/CheckinPicker';
import type { CheckinValues } from '@/components/journal/CheckinPicker';
import { EditorToolbar } from '@/components/journal/EditorToolbar';
// Also in MarkdownEditor, which is loaded lazily; kept here so the fallback needs no editor code.
const JOURNAL_PLACEHOLDER = 'Write about your day…   **bold**  # heading  - list  - [ ] task  > quote';
import { MarkdownView } from '@/components/journal/MarkdownView';
import { commandFor } from '@/components/journal/markdownCommands';
import type { Command } from '@/components/journal/markdownCommands';
import type { JournalCheckin, JournalEntry } from '@/types/api';

const MarkdownEditor = React.lazy(() =>
  import('@/components/journal/MarkdownEditor').then(module => ({ default: module.MarkdownEditor })),
);

class EditorBoundary extends React.Component<
  { fallback: React.ReactNode; children: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function entryText(entry: JournalEntry): string {
  return entry.text ?? entry.lines.join('\n');
}

function checkinLabel(checkin: JournalCheckin | undefined): string {
  if (!checkin) return '';
  const parts = [
    ['energy', checkin.energy],
    ['mood', checkin.mood],
    ['sleep', checkin.sleep_quality],
    ['stress', checkin.stress],
    ['focus', checkin.focus],
  ].filter((part): part is [string, number] => typeof part[1] === 'number');
  return parts.map(([name, value]) => `${name} ${value}`).join(' · ');
}

function payloadCheckin(value: CheckinValues): JournalCheckin | undefined {
  const checkin: JournalCheckin = {};
  (Object.keys(value) as (keyof CheckinValues)[]).forEach(key => {
    if (value[key] != null) checkin[key] = value[key];
  });
  return Object.keys(checkin).length ? checkin : undefined;
}

export function JournalScreen() {
  const { data, isPending, isError, refetch, fetchNextPage, hasNextPage, isFetchingNextPage } = useJournal();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const [text, setText] = React.useState('');
  const [selection, setSelection] = React.useState({ start: 0, end: 0 });
  const [checkin, setCheckin] = React.useState<CheckinValues>(emptyCheckin);
  const [saving, setSaving] = React.useState(false);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const fallbackRef = React.useRef<HTMLTextAreaElement>(null);

  const target = params.get('entry');
  const entries = React.useMemo(() => data?.pages.flatMap(p => p.entries) ?? [], [data]);
  const found = !target || entries.some(e => e.id === target);
  const canSave = text.trim().length > 0 || Object.values(checkin).some(value => value != null);

  React.useEffect(() => {
    if (target && !found && hasNextPage && !isFetchingNextPage) fetchNextPage();
  }, [target, found, hasNextPage, isFetchingNextPage, fetchNextPage]);

  React.useEffect(() => {
    if (target && found) {
      document.getElementById(`entry-${target}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }, [target, found]);

  const apply = (command: Command) => {
    const field = fallbackRef.current;
    const start = field?.selectionStart ?? selection.start;
    const end = field?.selectionEnd ?? selection.end;
    const next = command(text, start, end);
    setSelection({ start: next.start, end: next.end });
    setText(next.text);
    if (field) {
      requestAnimationFrame(() => {
        field.focus();
        field.setSelectionRange(next.start, next.end);
      });
    }
  };

  if (isPending) return <LoadingState label="Iris is opening your journal…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  const recurringPhrases = data.pages[0]?.recurringPhrases;

  const save = async () => {
    if (!canSave) return;
    setSaving(true);
    setSaveError(null);
    try {
      const chosen = payloadCheckin(checkin);
      await createEntry({ text, format: 'markdown', ...(chosen ? { checkin: chosen } : {}) });
      setText('');
      setSelection({ start: 0, end: 0 });
      setCheckin(emptyCheckin());
      qc.invalidateQueries({ queryKey: qk.journal });
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const fallback = (
    <textarea
      ref={fallbackRef}
      aria-label="journal entry"
      value={text}
      placeholder={JOURNAL_PLACEHOLDER}
      onChange={event => setText(event.target.value)}
      onSelect={event => setSelection({
        start: event.currentTarget.selectionStart,
        end: event.currentTarget.selectionEnd,
      })}
      onKeyDown={event => {
        const command = commandFor(event);
        if (!command) return;
        event.preventDefault();
        apply(command);
      }}
      style={{
        width: '100%',
        height: '100%',
        minHeight: 280,
        resize: 'none',
        background: 'transparent',
        border: 'none',
        outline: 'none',
        color: 'var(--ink)',
        fontFamily: 'var(--serif)',
        fontSize: 20,
        lineHeight: 1.55,
      }}
    />
  );

  return (
    <div className="row" style={{ height: '100%', minHeight: 0 }}>
      <div className="col" style={{ flex: 1, padding: '28px 48px 24px', minWidth: 0, minHeight: 0 }}>
        <div className="row" style={{ alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 18 }}>
          <div className="col" style={{ gap: 6 }}>
            <div className="kicker">today</div>
            <h1 className="serif" style={{ margin: 0, fontSize: 48, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
              Write it <span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>down.</span>
            </h1>
          </div>
          <button className="btn primary" onClick={save} disabled={saving || !canSave}>
            {saving ? 'Saving…' : 'Save entry'}
          </button>
        </div>
        <CheckinPicker value={checkin} onChange={setCheckin} />
        {/* One visible pane: its toolbar along the top edge, the page to write on
            below. Without a surface of its own the editor read as empty space. */}
        <div className="journal-pane col" style={{ flex: 1, minHeight: 320, marginTop: 16 }}>
          <EditorToolbar onCommand={apply} />
          <div style={{ flex: 1, minHeight: 280, padding: '14px 22px 0' }}>
          <EditorBoundary fallback={fallback}>
            <React.Suspense fallback={fallback}>
              <MarkdownEditor
                value={text}
                selection={selection}
                onChange={setText}
                onSelect={(start, end) => setSelection({ start, end })}
              />
            </React.Suspense>
          </EditorBoundary>
          </div>
        </div>
        {saveError && (
          <div role="alert" style={{ marginTop: 8, fontSize: 12, color: 'var(--rose)', fontFamily: 'var(--mono)' }}>
            Not saved: {saveError}
          </div>
        )}
      </div>

      <aside style={{ width: 380, flexShrink: 0, borderLeft: '1px dashed var(--line)', padding: '32px 28px', overflow: 'auto' }}>
        <div className="kicker" style={{ marginBottom: 8 }}>your entries · newest first</div>
        <h3 className="serif" style={{ margin: '0 0 22px', fontSize: 24, lineHeight: 1 }}>
          {entries.length} shown{hasNextPage ? '' : ', all of them'}
        </h3>
        <div className="col" style={{ gap: 22 }}>
          {entries.map(entry => {
            const highlighted = entry.id === target;
            const body = entryText(entry);
            const recorded = checkinLabel(entry.checkin);
            return (
              <article
                key={entry.id}
                id={`entry-${entry.id}`}
                className="col"
                style={{
                  gap: 6,
                  ...(highlighted ? {
                    margin: '0 -10px', padding: '10px', borderRadius: 8,
                    background: 'rgba(169,200,163,0.06)', border: '1px solid var(--sage-dim)',
                  } : {}),
                }}
              >
                <div className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between' }}>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                    {entry.occurredOn ? formatEventDate(entry.occurredOn) : 'undated'}
                  </span>
                  <div className="row" style={{ gap: 4 }}>
                    {(entry.tags ?? []).map(tag => (
                      <span key={tag} style={{ fontSize: 9, fontFamily: 'var(--mono)', color: 'var(--ink-4)' }}>·{tag}</span>
                    ))}
                  </div>
                </div>
                {recorded && (
                  <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)' }}>{recorded}</div>
                )}
                {entry.format === 'markdown'
                  ? <MarkdownView text={body} />
                  : <div style={{ fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.55, whiteSpace: 'pre-wrap' }}>{body}</div>}
                {entry.audioUrl && (
                  <audio controls preload="none" src={entry.audioUrl} aria-label="the recording this was transcribed from"
                         style={{ width: 320, height: 28, marginTop: 2 }} />
                )}
                {entry.irisNote && (
                  <div className="row" style={{ gap: 6, alignItems: 'flex-start', marginTop: 4, paddingLeft: 10, borderLeft: '1px solid var(--sage-dim)' }}>
                    <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--sage)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>iris:</span>
                    <span style={{ fontSize: 11, color: 'var(--ink-2)', fontStyle: 'italic' }}>{entry.irisNote}</span>
                  </div>
                )}
              </article>
            );
          })}
        </div>
        <div className="row" style={{ marginTop: 20, justifyContent: 'center' }}>
          {hasNextPage ? (
            <button className="btn" onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
              {isFetchingNextPage ? 'Loading…' : 'older entries ↓'}
            </button>
          ) : (
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
              back to the beginning
            </span>
          )}
        </div>
        {recurringPhrases && recurringPhrases.length > 0 && (
          <>
            <hr className="dotline" style={{ margin: '28px 0 18px' }} />
            <div className="kicker" style={{ marginBottom: 10 }}>phrases iris keeps hearing</div>
            <div className="col" style={{ gap: 6 }}>
              {recurringPhrases.map((phrase, index) => (
                <div key={index} className="row" style={{ alignItems: 'baseline', gap: 10 }}>
                  <span style={{ flex: 1, fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: 14, color: 'var(--ink)' }}>"{phrase.phrase}"</span>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)' }}>×{phrase.count}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </aside>
    </div>
  );
}

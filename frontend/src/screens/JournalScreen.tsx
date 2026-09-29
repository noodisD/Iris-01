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
import { Badge, Button, Page, TabPanel, Tabs } from '@/ui';
import styles from './JournalScreen.module.css';
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
  const [params, setParams] = useSearchParams();
  const [text, setText] = React.useState('');
  const [selection, setSelection] = React.useState({ start: 0, end: 0 });
  const [checkin, setCheckin] = React.useState<CheckinValues>(emptyCheckin);
  const [saving, setSaving] = React.useState(false);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const fallbackRef = React.useRef<HTMLTextAreaElement>(null);

  const target = params.get('entry');
  // Writing and reading are separate pages: the history beside the editor
  // took the room writing needs. A link to one entry opens the history.
  const view: 'write' | 'entries' = target || params.get('view') === 'entries' ? 'entries' : 'write';
  const show = (next: 'write' | 'entries') => setParams(next === 'entries' ? { view: 'entries' } : {});
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
      qc.invalidateQueries({ queryKey: qk.patterns });
      qc.invalidateQueries({ queryKey: qk.dayDifferencesRoot });
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
      className={styles.fallback}
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
    />
  );

  return (
    <Page title="Journal" lead={new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}
      width="standard"
      actions={view === 'write' && (
        <Button variant="primary" onClick={save} disabled={saving || !canSave}>{saving ? 'Saving…' : 'Save entry'}</Button>
      )}>
      <Tabs label="Journal" value={view} onChange={show}
        tabs={[{ value: 'write', label: 'Write' }, { value: 'entries', label: 'Entries' }]}>
        <TabPanel value="write">
          <div className={styles.write}>
            <CheckinPicker value={checkin} onChange={setCheckin} />
            {/* One visible pane: its toolbar along the top edge, the page to
                write on below. */}
            <div className={styles.pane}>
              <EditorToolbar onCommand={apply} />
              <div className={styles.editor}>
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
            {saveError && <p role="alert" className={styles.error}>Not saved: {saveError}</p>}
          </div>
        </TabPanel>

        <TabPanel value="entries">
          <section aria-label="Your entries" className={styles.entries}>
            <p className={styles.count}>{entries.length} shown, newest first{hasNextPage ? '' : ', all of them'}</p>
            {entries.map(entry => {
              const body = entryText(entry);
              const recorded = checkinLabel(entry.checkin);
              return (
                <article key={entry.id} id={`entry-${entry.id}`}
                  className={`${styles.entry} ${entry.id === target ? styles.target : ''}`}>
                  <header className={styles.entryHead}>
                    <h2 className={styles.date}>{entry.occurredOn ? formatEventDate(entry.occurredOn) : 'undated'}</h2>
                    {(entry.tags ?? []).map(tag => <Badge key={tag}>{tag}</Badge>)}
                  </header>
                  {recorded && <p className={styles.recorded}>{recorded}</p>}
                  {entry.format === 'markdown'
                    ? <div className={styles.text}><MarkdownView text={body} /></div>
                    : <div className={styles.text}>{body}</div>}
                  {entry.audioUrl && (
                    <audio controls preload="none" src={entry.audioUrl} aria-label="the recording this was transcribed from"
                      className={styles.audio} />
                  )}
                  {entry.irisNote && <p className={styles.note}><strong>Iris:</strong> {entry.irisNote}</p>}
                </article>
              );
            })}
            <div className={styles.more}>
              {hasNextPage
                ? <Button onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>{isFetchingNextPage ? 'Loading…' : 'Show older entries'}</Button>
                : <p className={styles.count}>That's the first entry.</p>}
            </div>
            {recurringPhrases && recurringPhrases.length > 0 && (
              <section aria-label="Phrases you repeat" className={styles.phrases}>
                <h2 className={styles.phrasesTitle}>Phrases you repeat</h2>
                <ul>
                  {recurringPhrases.map((phrase, index) => (
                    <li key={index}><span>&ldquo;{phrase.phrase}&rdquo;</span><span className={styles.times}>{phrase.count} times</span></li>
                  ))}
                </ul>
              </section>
            )}
          </section>
        </TabPanel>
      </Tabs>
    </Page>
  );
}

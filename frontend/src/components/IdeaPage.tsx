import React from 'react';
import { Link } from 'react-router-dom';
import { Pencil } from 'lucide-react';
import { updateIdea } from '@/api/ideas';
import { MarkdownEditor } from '@/components/journal/MarkdownEditor';
import { MarkdownView, type WikilinkRenderer } from '@/components/journal/MarkdownView';
import { useSaveIdeaNotes, useUpdateIdea } from '@/hooks/useIdeas';
import { Button } from '@/ui';
import styles from './IdeaPage.module.css';
import type { IdeaPage as Page, IdeaSummary } from '@/types/api';

const STATEMENT_LIMIT = 600;
const NOTES_LIMIT = 20000;
const AUTOSAVE_MS = 900;

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'That did not save.';
}

/**
 * An idea's wording, which the owner can rewrite in place. Enter saves, Escape
 * keeps the old wording. Links to it in other notes follow the new wording.
 */
export function EditableStatement({ idea }: { idea: IdeaSummary }) {
  const update = useUpdateIdea();
  const [draft, setDraft] = React.useState<string | null>(null);
  const field = React.useRef<HTMLTextAreaElement>(null);
  const editing = draft !== null;

  React.useEffect(() => {
    if (editing) field.current?.select();
  }, [editing]);

  const cancel = () => { setDraft(null); update.reset(); };
  const save = () => {
    const wording = (draft ?? '').replace(/\s+/g, ' ').trim();
    if (!wording || wording === idea.statement) { cancel(); return; }
    update.mutate({ id: idea.id, body: { statement: wording } }, { onSuccess: () => setDraft(null) });
  };

  if (!editing) {
    return (
      <span className={styles.statement}>
        <span onDoubleClick={() => setDraft(idea.statement)}>{idea.statement}</span>
        <button type="button" className={styles.rename} onClick={() => setDraft(idea.statement)}
          aria-label="Rename this idea" title="Rename">
          <Pencil size={16} aria-hidden="true" />
        </button>
      </span>
    );
  }
  return (
    <span className={styles.statementEdit}>
      <textarea ref={field} className={styles.statementField} aria-label="Wording of this idea" rows={2}
        value={draft} maxLength={STATEMENT_LIMIT} disabled={update.isPending}
        onChange={event => setDraft(event.target.value)}
        onKeyDown={event => {
          if (event.key === 'Enter') { event.preventDefault(); save(); }
          if (event.key === 'Escape') { event.preventDefault(); cancel(); }
        }} />
      <span className={styles.statementActions}>
        <Button size="sm" variant="primary" disabled={update.isPending} onClick={save}>Save wording</Button>
        <Button size="sm" variant="quiet" disabled={update.isPending} onClick={cancel}>Cancel</Button>
        <span className={styles.hint}>Enter saves, Escape cancels.</span>
      </span>
      {update.error && <span role="alert" className={styles.error}>{message(update.error)}</span>}
    </span>
  );
}

type SaveState = 'saved' | 'saving' | 'waiting' | 'failed';

/**
 * The owner's notes on an idea, written like a page in a notebook. `[[` offers
 * the other ideas; a link goes to that idea's page. Writing saves itself.
 */
export function IdeaNotes({ id, page, statements }: { id: string; page: Page; statements: string[] }) {
  const save = useSaveIdeaNotes(id);
  const [draft, setDraft] = React.useState<string | null>(null);
  const [selection, setSelection] = React.useState({ start: 0, end: 0 });
  const [state, setState] = React.useState<SaveState>('saved');
  const saved = React.useRef(page.notes);
  const latest = React.useRef<string | null>(null);
  latest.current = draft;

  const persist = React.useCallback((text: string, after?: () => void) => {
    if (text === saved.current) { after?.(); return; }
    setState('saving');
    save.mutate(text, {
      onSuccess: () => {
        saved.current = text;
        setState(latest.current === null || latest.current === text ? 'saved' : 'waiting');
        after?.();
      },
      onError: () => setState('failed'),
    });
  }, [save]);

  React.useEffect(() => {
    if (draft === null || draft === saved.current) return undefined;
    setState('waiting');
    const timer = window.setTimeout(() => persist(draft), AUTOSAVE_MS);
    return () => window.clearTimeout(timer);
    // `persist` changes with the mutation's state; the timer only follows the text.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  // Leaving the page mid-sentence still keeps the sentence.
  React.useEffect(() => () => {
    const text = latest.current;
    if (text !== null && text !== saved.current) void updateIdea(id, { notes: text }).catch(() => undefined);
  }, [id]);

  const open = () => {
    saved.current = page.notes;
    setSelection({ start: page.notes.length, end: page.notes.length });
    setDraft(page.notes);
    setState('saved');
  };
  const done = () => {
    if (draft === null) return;
    persist(draft, () => { setDraft(null); void save.refresh(); });
  };

  const wikilink: WikilinkRenderer = (target, shown, key) => {
    const linked = page.links[target];
    return linked
      ? <Link key={key} to={`/ideas/${linked}`} className={styles.wikilink}>{shown}</Link>
      : <span key={key} className={styles.unlinked} title="No idea has this wording yet">{shown}</span>;
  };

  if (draft === null) {
    return (
      <section className={styles.notes} aria-labelledby="idea-notes">
        <div className={styles.notesHead}>
          <h2 id="idea-notes" className={styles.title}>Notes</h2>
          <Button size="sm" variant="quiet" icon={<Pencil size={14} aria-hidden="true" />} onClick={open}>
            {page.notes ? 'Edit notes' : 'Write notes'}
          </Button>
        </div>
        {page.notes.trim() ? (
          <div className={styles.page} onClick={event => {
            if (!(event.target as HTMLElement).closest('a')) open();
          }}>
            <MarkdownView text={page.notes} wikilink={wikilink} />
          </div>
        ) : (
          <button type="button" className={styles.blank} onClick={open}>
            What do you think about this idea, and why? Type [[ to link another idea.
          </button>
        )}
      </section>
    );
  }

  return (
    <section className={styles.notes} aria-labelledby="idea-notes">
      <div className={styles.notesHead}>
        <h2 id="idea-notes" className={styles.title}>Notes</h2>
        <span className={styles.status} role="status">
          {state === 'saving' ? 'Saving…' : state === 'waiting' ? 'Editing' : state === 'failed' ? '' : 'Saved'}
        </span>
        <Button size="sm" variant="primary" disabled={save.isPending} onClick={done}>Done</Button>
      </div>
      <div className={`${styles.page} ${styles.editing}`}>
        <MarkdownEditor value={draft} selection={selection} label="Notes on this idea"
          placeholderText="Write freely. **bold**  # heading  - list  > quote   [[ links an idea"
          linkTargets={statements} fontSize={18} minHeight={220}
          onChange={text => setDraft(text.slice(0, NOTES_LIMIT))}
          onSelect={(start, end) => setSelection({ start, end })} />
      </div>
      {state === 'failed' && (
        <p role="alert" className={styles.error}>
          {message(save.error)} Your text is still here; keep writing or press Done to try again.
        </p>
      )}
    </section>
  );
}

/** Ideas whose notes link to this one, as Obsidian lists linked mentions. */
export function Backlinks({ page }: { page: Page }) {
  return (
    <section className={styles.backlinks} aria-labelledby="idea-backlinks">
      <h2 id="idea-backlinks" className={styles.title}>
        Linked from <span className={styles.count}>{page.backlinks.length}</span>
      </h2>
      {page.backlinks.length === 0 ? (
        <p className={styles.hint}>No other idea's notes link here yet.</p>
      ) : (
        <ul className={styles.backlinkList}>
          {page.backlinks.map(row => (
            <li key={row.id}>
              <Link to={`/ideas/${row.id}`} className={styles.backlink}>{row.statement}</Link>
              {row.status === 'candidate' && <span className={styles.hint}> (waiting in review)</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

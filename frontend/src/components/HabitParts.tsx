import React from 'react';
import { useDeleteHabit, useHabitDays, useSetHabitDay, useUpdateHabit } from '@/hooks/useHabits';
import { color } from '@/components/primitives';
import type { Habit, HabitDay, HabitFrequency } from '@/types/api';
import { Button, ChoiceGroup, Field, Section } from '@/ui';
import styles from './HabitParts.module.css';

/** Shared by the Habits list (edited in place) and a habit's own page. */
export const PERIODS: { value: HabitFrequency; label: string; noun: string; adverb: string }[] = [
  { value: 'daily', label: 'Daily', noun: 'day', adverb: 'today' },
  { value: 'weekly', label: 'Weekly', noun: 'week', adverb: 'this week' },
  { value: 'monthly', label: 'Monthly', noun: 'month', adverb: 'this month' },
];

export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const STATUSES = [
  { value: 'done', label: 'Done' },
  { value: 'skipped', label: 'Skipped' },
  { value: 'none', label: 'Not done' },
] as const;

function monthDays(year: number, month: number): Date[] {
  const days: Date[] = [];
  for (let d = new Date(year, month, 1); d.getMonth() === month; d = new Date(year, month, d.getDate() + 1)) days.push(d);
  return days;
}

/** One day: done, skipped or neither, and that day's note. Future days cannot be marked. */
export function DayEditor({ habit, date, day, onClose }: { habit: Habit; date: string; day?: HabitDay; onClose: () => void }) {
  const save = useSetHabitDay(habit.id);
  const [status, setStatus] = React.useState<HabitDay['status']>(day?.status ?? 'none');
  const [note, setNote] = React.useState(day?.note ?? '');
  React.useEffect(() => { setStatus(day?.status ?? 'none'); setNote(day?.note ?? ''); }, [date, day?.status, day?.note]);
  const label = new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });
  const changed = status !== (day?.status ?? 'none') || note.trim() !== (day?.note ?? '');
  return (
    <section className={styles.editor} aria-label={`${habit.name} on ${label}`}>
      <div className={styles.editorSide}>
        <h3 className={styles.editorTitle}>{label}</h3>
        <ChoiceGroup label="What happened" options={[...STATUSES]} value={status} onChange={v => v && setStatus(v)} />
      </div>
      <div className={styles.editorNote}>
        <Field label="Note for this day" hint="A line of reflection, if you have one. IRIS can recall it in chat.">
          <textarea value={note} onChange={e => setNote(e.target.value)} className={styles.note}
            rows={Math.max(8, note.split('\n').length + 1)}
            placeholder={status === 'skipped' ? 'Why you skipped it, if you like' : 'How it went'} />
        </Field>
      </div>
      <div className={`${styles.row} ${styles.editorActions}`}>
        <Button variant="primary" disabled={!changed || save.isPending}
          onClick={() => save.mutate({ date, status, note: note.trim() || null }, { onSuccess: onClose })}>
          {save.isPending ? 'Saving…' : 'Save day'}
        </Button>
        <Button variant="quiet" onClick={onClose}>Close</Button>
      </div>
      {save.isError && <p role="alert" className={styles.error}>That day wasn't saved: {save.error instanceof Error ? save.error.message : 'try again'}.</p>}
    </section>
  );
}

export function Calendar({ habit }: { habit: Habit }) {
  const today = new Date();
  const [cursor, setCursor] = React.useState({ year: today.getFullYear(), month: today.getMonth() });
  const [selected, setSelected] = React.useState<string | null>(null);
  const days = monthDays(cursor.year, cursor.month);
  const start = isoDate(days[0]), end = isoDate(days[days.length - 1]);
  const { data } = useHabitDays(habit.id, start, end);
  const byDate = new Map((data ?? []).map(d => [d.date, d]));
  const c = color(habit.color);
  const todayIso = isoDate(today);
  const title = new Date(cursor.year, cursor.month, 1).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  const move = (delta: number) => {
    const d = new Date(cursor.year, cursor.month + delta, 1);
    setCursor({ year: d.getFullYear(), month: d.getMonth() });
    setSelected(null);
  };
  const atCurrentMonth = cursor.year === today.getFullYear() && cursor.month === today.getMonth();
  const lead = (days[0].getDay() + 6) % 7;

  return (
    <Section title="Days" actions={
      <div className={styles.row}>
        <Button size="sm" variant="quiet" onClick={() => move(-1)} aria-label="Previous month">‹</Button>
        <span className={styles.month}>{title}</span>
        <Button size="sm" variant="quiet" onClick={() => move(1)} disabled={atCurrentMonth} aria-label="Next month">›</Button>
      </div>}>
      <div className={styles.grid} role="grid" aria-label={`${habit.name}, ${title}`}>
        {WEEKDAYS.map(w => <span key={w} className={styles.weekday} role="columnheader">{w}</span>)}
        {Array.from({ length: lead }, (_, i) => <span key={`lead-${i}`} />)}
        {days.map(d => {
          const key = isoDate(d);
          const day = byDate.get(key);
          const future = key > todayIso;
          const status = day?.status ?? 'none';
          return (
            <button key={key} type="button" role="gridcell" disabled={future}
              aria-label={`${d.getDate()}: ${status === 'done' ? 'done' : status === 'skipped' ? 'skipped' : 'not done'}${day?.note ? ', with a note' : ''}`}
              aria-pressed={selected === key}
              className={`${styles.cell} ${status === 'skipped' ? styles.skipped : ''} ${key === todayIso ? styles.today : ''} ${selected === key ? styles.selected : ''}`}
              style={status === 'done' ? { background: c, borderColor: c, color: 'var(--night)' } : status === 'skipped' ? { borderColor: c } : undefined}
              onClick={() => setSelected(key)}>
              {d.getDate()}
              {day?.note && <span className={styles.noteDot} aria-hidden />}
            </button>
          );
        })}
      </div>
      <p className={styles.legend}>Filled: done. Outlined: skipped, a rest that does not break a daily streak. A dot: there is a note.</p>
      {selected && <DayEditor habit={habit} date={selected} day={byDate.get(selected)} onClose={() => setSelected(null)} />}
    </Section>
  );
}

export function EditHabit({ habit, onSaved, onDeleted }: {
  habit: Habit; onSaved?: (h: Habit) => void; onDeleted?: () => void;
}) {
  const update = useUpdateHabit(habit.id);
  const remove = useDeleteHabit(habit.id);
  const [name, setName] = React.useState(habit.name);
  const [intent, setIntent] = React.useState(habit.intent ?? '');
  const [tag, setTag] = React.useState(habit.tag ?? '');
  const [frequency, setFrequency] = React.useState<HabitFrequency>(habit.frequency ?? 'daily');
  const [target, setTarget] = React.useState(habit.target ?? 1);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const changed = name.trim() !== habit.name || intent.trim() !== (habit.intent ?? '') || tag.trim() !== (habit.tag ?? '')
    || frequency !== (habit.frequency ?? 'daily') || (frequency !== 'daily' && target !== (habit.target ?? 1));
  const noun = PERIODS.find(p => p.value === frequency)!.noun;

  return (
    <Section title="The habit">
      <form className={styles.form} onSubmit={e => {
        e.preventDefault();
        if (!name.trim()) return;
        update.mutate({ name: name.trim(), intent: intent.trim() || null, tag: tag.trim() || null, frequency,
          ...(frequency !== 'daily' ? { target } : {}) },
        { onSuccess: h => onSaved?.(h) });
      }}>
        <div className={styles.fields}>
          <Field label="Name"><input value={name} onChange={e => setName(e.target.value)} /></Field>
          <Field label="What it is for"><input value={intent} onChange={e => setIntent(e.target.value)} /></Field>
          <Field label="Tag"><input value={tag} onChange={e => setTag(e.target.value)} /></Field>
        </div>
        <ChoiceGroup label="How often" options={PERIODS.map(p => ({ value: p.value, label: p.label }))}
          value={frequency} onChange={v => v && setFrequency(v)} />
        {frequency !== 'daily' && (
          <Field label={`Times a ${noun}`}>
            <input type="number" min={1} max={31} value={target}
              onChange={e => setTarget(Math.max(1, Math.min(31, Number(e.target.value) || 1)))} />
          </Field>
        )}
        <div className={styles.row}>
          <Button variant="primary" type="submit" disabled={!changed || !name.trim() || update.isPending}>Save changes</Button>
          <Button variant="quiet" type="button" onClick={() => update.mutate({ archived: !habit.archived })}>
            {habit.archived ? 'Restore from archive' : 'Archive'}
          </Button>
          {!confirmDelete ? (
            <Button variant="quiet" type="button" onClick={() => setConfirmDelete(true)}>Delete…</Button>
          ) : (
            <>
              <span className={styles.warn}>Delete {habit.name} and every day of it? Archive keeps the history.</span>
              <Button type="button" onClick={() => remove.mutate(undefined, { onSuccess: () => onDeleted?.() })}>
                Delete for good
              </Button>
              <Button variant="quiet" type="button" onClick={() => setConfirmDelete(false)}>Keep it</Button>
            </>
          )}
        </div>
        {(update.isError || remove.isError) && <p role="alert" className={styles.error}>That didn't save. Try again.</p>}
      </form>
    </Section>
  );
}

/** One day opened from the list: its saved status and note are read, then edited in place. */
export function DayEditorLoader({ habit, date, onClose }: { habit: Habit; date: string; onClose: () => void }) {
  const { data, isLoading } = useHabitDays(habit.id, date, date);
  if (isLoading) return <p className={styles.legend} role="status">Opening {date}…</p>;
  return <DayEditor habit={habit} date={date} day={data?.[0]} onClose={onClose} />;
}

import React from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { Calendar, DayEditorLoader, EditHabit, PERIODS, isoDate } from '@/components/HabitParts';
import { useAllHabits, useCreateHabit, useOrderHabits, useToggleHabit, useToggleHabitDay } from '@/hooks/useHabits';
import { ChevronDown, ChevronUp, GripVertical } from 'lucide-react';
import { LoadingState, ErrorState } from '@/components/states';
import { color } from '@/components/primitives';
import type { Habit, HabitFrequency } from '@/types/api';
import { Button, ChoiceGroup, IconButton, Page, Tabs, TabPanel } from '@/ui';
import styles from './HabitsScreen.module.css';

function frequencyOf(h: Habit): HabitFrequency {
  return h.frequency ?? 'daily';
}

function plural(n: number, one: string) {
  return `${n} ${one}${n === 1 ? '' : 's'}`;
}

/** Weeks or months as small cells: filled when the target was met, partly when begun. */
function PeriodStrip({ h, c }: { h: Habit; c: string }) {
  const periods = h.periods ?? [];
  const target = h.target ?? 1;
  const unit = frequencyOf(h) === 'weekly' ? 'week' : 'month';
  return (
    <div className={styles.history} aria-label={`Last ${periods.length} ${unit}s: ${periods.filter(p => p.met).length} on target`}>
      <div className={styles.cells}>
        {periods.map(p => (
          <span key={p.start} className={styles.cell} title={`${p.start}: ${p.done} of ${target}`}
            style={p.met ? { background: c } : p.done > 0 ? { borderColor: c } : undefined} />
        ))}
      </div>
      <div className={styles.axis}><span>{plural(periods.length, unit)} ago</span><span>Now</span></div>
    </div>
  );
}

function dayAt(start: string | undefined, index: number, length: number): string {
  // The server says where the window starts; without it, count back from today.
  const base = start ? new Date(`${start}T12:00:00`) : new Date(Date.now() - (length - 1) * 86400000);
  return isoDate(new Date(base.getFullYear(), base.getMonth(), base.getDate() + index));
}

/** The last 60 days, each a button: click one to mark it and write its note, here. */
/** How long a click waits to see whether it is the first of a double-click. */
const DOUBLE_CLICK_MS = 250;

function DayDots({ h, c, selected, onPick }: { h: Habit; c: string; selected: string | null; onPick: (date: string) => void }) {
  const status = h.recentStatus ?? h.recentDays.map(v => (v ? 'done' : 'none'));
  const notes = h.recentNotes ?? [];
  const toggle = useToggleHabitDay();
  // One click opens the day; a double-click marks it done (or not done) at once.
  // The single click waits a moment so a double-click never flashes the editor open.
  const pending = React.useRef<number | null>(null);
  React.useEffect(() => () => { if (pending.current) window.clearTimeout(pending.current); }, []);
  const click = (date: string) => {
    if (pending.current) window.clearTimeout(pending.current);
    pending.current = window.setTimeout(() => { pending.current = null; onPick(date); }, DOUBLE_CLICK_MS);
  };
  const doubleClick = (date: string, done: boolean) => {
    if (pending.current) { window.clearTimeout(pending.current); pending.current = null; }
    toggle.mutate({ id: h.id, date, done: !done });
  };
  return (
    <div className={styles.history}>
      <div className={styles.dots} role="group" aria-label={`Last ${status.length} days: ${status.filter(s => s === 'done').length} done. Choose a day to change it.`}>
        {status.map((s, i) => {
          const date = dayAt(h.recentStart, i, status.length);
          const label = new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
          return (
            <button key={date} type="button" onClick={() => click(date)} onDoubleClick={() => doubleClick(date, s === 'done')}
              title={`${label}: click for the note, double-click to mark ${s === 'done' ? 'not done' : 'done'}`}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); onPick(date); } }}
              aria-pressed={selected === date}
              aria-label={`${label}: ${s === 'done' ? 'done' : s === 'skipped' ? 'skipped' : 'not done'}${notes[i] ? ', with a note' : ''}`}
              className={`${styles.day} ${s === 'skipped' ? styles.daySkipped : ''} ${notes[i] ? styles.dayNoted : ''} ${selected === date ? styles.daySelected : ''}`}
              style={s === 'done' ? { background: c } : s === 'skipped' ? { borderColor: c } : undefined} />
          );
        })}
      </div>
      <div className={styles.axis}><span>{status.length} days ago</span><span>Today</span></div>
      {toggle.isError && <p role="alert" className={styles.error}>That day didn't save; it's back as it was.</p>}
    </div>
  );
}

interface Ordering {
  index: number; count: number;
  move: (from: number, to: number) => void;
  dragged: React.MutableRefObject<number | null>;
}

function HabitRow({ h, onToggle, order }: { h: Habit; onToggle: (id: string, done: boolean) => void; order?: Ordering }) {
  const c = color(h.color);
  const navigate = useNavigate();
  const frequency = frequencyOf(h);
  const period = PERIODS.find(p => p.value === frequency)!;
  const target = h.target ?? 1;
  const [day, setDay] = React.useState<string | null>(null);
  const [open, setOpen] = React.useState(false);
  const [over, setOver] = React.useState(false);
  const article = React.useRef<HTMLElement>(null);
  return (
    <article ref={article} className={`${styles.item} ${over ? styles.dropTarget : ''}`} aria-label={h.name}
      onDragOver={order ? e => { if (order.dragged.current !== null) { e.preventDefault(); setOver(true); } } : undefined}
      onDragLeave={() => setOver(false)}
      onDrop={order ? e => {
        e.preventDefault(); setOver(false);
        if (order.dragged.current !== null) order.move(order.dragged.current, order.index);
        order.dragged.current = null;
      } : undefined}>
      <div className={styles.row}>
        <div className={styles.what}>
          {order && order.count > 1 && (
            <div className={styles.order}>
              <span className={styles.grip} draggable title="Drag to move" aria-hidden
                onDragStart={e => {
                  order.dragged.current = order.index;
                  if (e.dataTransfer) {
                    e.dataTransfer.effectAllowed = 'move';
                    if (article.current) e.dataTransfer.setDragImage?.(article.current, 24, 24);
                  }
                }}
                onDragEnd={() => { order.dragged.current = null; }}>
                <GripVertical size={16} />
              </span>
              <IconButton label={`Move ${h.name} up`} icon={<ChevronUp size={14} />} disabled={order.index === 0}
                onClick={() => order.move(order.index, order.index - 1)} className={styles.moveButton} />
              <IconButton label={`Move ${h.name} down`} icon={<ChevronDown size={14} />} disabled={order.index === order.count - 1}
                onClick={() => order.move(order.index, order.index + 1)} className={styles.moveButton} />
            </div>
          )}
          <button onClick={() => onToggle(h.id, !h.doneToday)} aria-label={`Mark ${h.name} ${h.doneToday ? 'not done' : 'done'} today`}
            aria-pressed={h.doneToday} className={styles.tick}
            style={{ borderColor: h.doneToday ? c : undefined, background: h.doneToday ? c : undefined }}>
            {h.doneToday && <span aria-hidden>✓</span>}
          </button>
          <div className={styles.names}>
            <button type="button" className={styles.name} aria-expanded={open} onClick={() => setOpen(o => !o)}
              title="Show the calendar and edit this habit">{h.name}</button>
            {h.tag && <span className={styles.tag}>{h.tag}</span>}
            {h.intent && <span className={styles.intent}>{h.intent}</span>}
            {frequency !== 'daily' && (
              <span className={h.periodMet ? styles.progressMet : styles.progress}>
                {h.periodDone ?? 0} of {target} {period.adverb}
              </span>
            )}
          </div>
        </div>

        <div className={styles.middle}>
          <DayDots h={h} c={c} selected={day} onPick={d => setDay(cur => (cur === d ? null : d))} />
          {frequency !== 'daily' && <PeriodStrip h={h} c={c} />}
        </div>

        <div className={styles.streak}>
          <span className={styles.streakNumber} style={{ color: h.streakDays === 0 ? undefined : c }}>{h.streakDays}</span>
          <span className={styles.streakLabel}>{h.streakUnit ?? 'day'} streak, best {h.bestStreak}</span>
        </div>
      </div>

      {day && <div className={styles.inline}><DayEditorLoader key={day} habit={h} date={day} onClose={() => setDay(null)} noteOnly /></div>}
      {open && (
        <div className={`${styles.inline} ${styles.expanded}`}>
          <Calendar habit={h} />
          <EditHabit key={h.id + (h.frequency ?? '')} habit={h}
            onSaved={saved => { if ((saved.frequency ?? 'daily') !== frequency) navigate(`/habits/${saved.frequency ?? 'daily'}`); }}
            onDeleted={() => setOpen(false)} />
          <Button variant="quiet" size="sm" onClick={() => setOpen(false)}>Close</Button>
        </div>
      )}
    </article>
  );
}

/** Constellation view: daily habits as circles sized by streak. */
function Constellation({ habits, onToggle }: { habits: Habit[]; onToggle: (id: string, done: boolean) => void }) {
  const W = 760, H = 420;
  const positions: Record<string, { x: number; y: number; r: number }> = {};
  habits.forEach((h, i) => {
    const angle = (i / habits.length) * Math.PI * 2 - Math.PI / 2;
    positions[h.id] = { x: W / 2 + Math.cos(angle) * 200, y: H / 2 + Math.sin(angle) * 150, r: 40 + (h.streakDays / 21) * 28 };
  });

  // Arranged in a ring and sized by streak, nothing more: no arrows between
  // habits, since nothing measures how one habit pulls on another.
  return (
    <figure className={styles.constellation}>
      <figcaption className={styles.caption}>Your daily habits, sized by current streak. Tap one to tick it.</figcaption>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} className={styles.sky} role="img" aria-label="Habits as circles sized by streak">
        {habits.map(h => {
          const p = positions[h.id], c = color(h.color), done = h.doneToday;
          return (
            <g key={h.id} onClick={() => onToggle(h.id, !done)} style={{ cursor: 'pointer' }}>
              <circle cx={p.x} cy={p.y} r={p.r + 8} fill="none" stroke={c} strokeWidth="1" opacity={done ? 0.4 : 0.1} />
              <circle cx={p.x} cy={p.y} r={p.r} fill={done ? c : 'var(--dusk)'} stroke={c} strokeWidth={done ? 0 : 1.5} opacity={done ? 0.92 : 1} />
              <text x={p.x} y={p.y - 2} textAnchor="middle" fontFamily="var(--font-read)" fontSize="15" fontStyle="italic" fill={done ? 'var(--night)' : 'var(--petal)'}>{h.name.split(' ')[0]}</text>
              <text x={p.x} y={p.y + 14} textAnchor="middle" fontFamily="var(--font-ui)" fontSize="10" fill={done ? 'var(--night)' : 'var(--petal-3)'}>{h.streakDays}d</text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

/** A name, how often, and optionally a tag. Nothing else is needed to start one. */
function AddHabit({ frequency }: { frequency: HabitFrequency }) {
  const create = useCreateHabit();
  const [name, setName] = React.useState('');
  const [tag, setTag] = React.useState('');
  const [target, setTarget] = React.useState(1);
  const period = PERIODS.find(p => p.value === frequency)!;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    create.mutate({ name: trimmed, tag: tag.trim() || undefined, frequency, target }, {
      onSuccess: () => { setName(''); setTag(''); setTarget(1); },
    });
  };

  return (
    <form onSubmit={submit} className={styles.add} aria-label={`Add a ${period.label.toLowerCase()} habit`}>
      <input aria-label="Habit name" placeholder={`A new ${period.label.toLowerCase()} habit`} value={name}
        onChange={e => setName(e.target.value)} className={styles.nameInput} />
      {frequency !== 'daily' && (
        <label className={styles.target}>
          <input aria-label={`Times a ${period.noun}`} type="number" min={1} max={31} value={target}
            onChange={e => setTarget(Math.max(1, Math.min(31, Number(e.target.value) || 1)))} />
          <span>times a {period.noun}</span>
        </label>
      )}
      <input aria-label="Tag" placeholder="Tag (optional)" value={tag} onChange={e => setTag(e.target.value)} className={styles.tagInput} />
      <Button variant="primary" type="submit" disabled={!name.trim() || create.isPending}>Add habit</Button>
      {create.isError && <span role="alert" className={styles.error}>It wasn't saved. Try again.</span>}
    </form>
  );
}

const VIEWS = [{ value: 'list', label: 'List' }, { value: 'constellation', label: 'Constellation' }] as const;

function PeriodPanel({ frequency, habits, onToggle }: {
  frequency: HabitFrequency; habits: Habit[]; onToggle: (id: string, done: boolean) => void;
}) {
  const [view, setView] = React.useState<'list' | 'constellation'>('list');
  const period = PERIODS.find(p => p.value === frequency)!;
  const order = useOrderHabits();
  const dragged = React.useRef<number | null>(null);
  const move = (from: number, to: number) => {
    if (from === to || to < 0 || to >= habits.length) return;
    const ids = habits.map(h => h.id);
    const [id] = ids.splice(from, 1);
    ids.splice(to, 0, id);
    order.mutate(ids);
  };
  const onTarget = habits.filter(h => (frequency === 'daily' ? h.doneToday : h.periodMet)).length;
  return (
    <div className={styles.panel}>
      <div className={styles.panelHead}>
        <p className={styles.summary}>
          {habits.length === 0 ? `No ${period.label.toLowerCase()} habits yet.`
            : frequency === 'daily' ? `${onTarget} of ${habits.length} done today.`
            : `${onTarget} of ${habits.length} on target ${period.adverb}.`}
        </p>
        {frequency === 'daily' && habits.length > 0 && (
          <ChoiceGroup label="View" options={[...VIEWS]} value={view} onChange={v => v && setView(v)} />
        )}
      </div>
      <AddHabit frequency={frequency} />
      {habits.length === 0 ? (
        <p className={styles.empty}>
          {frequency === 'daily' ? 'Name one above and tick it off here each day.'
            : `Name one above, say how many times a ${period.noun}, and tick it off on the days you do it.`}
        </p>
      ) : view === 'constellation' && frequency === 'daily' ? (
        <Constellation habits={habits} onToggle={onToggle} />
      ) : (
        <div className={styles.list}>
          {order.isError && <p role="alert" className={styles.error}>The new order wasn't saved; it's back as it was.</p>}
          {habits.map((h, index) => (
            <HabitRow key={h.id} h={h} onToggle={onToggle}
              order={{ index, count: habits.length, move, dragged }} />
          ))}
        </div>
      )}
    </div>
  );
}

/** An archived habit, restorable in place. */
function ArchivedHabit({ h }: { h: Habit }) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <button type="button" className={styles.archivedName} aria-expanded={open} onClick={() => setOpen(o => !o)}>{h.name}</button>
      {open && <div className={styles.inline}><EditHabit habit={h} onDeleted={() => setOpen(false)} /></div>}
    </>
  );
}

export function HabitsScreen() {
  const { period } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = useAllHabits();
  const toggle = useToggleHabit();

  if (!PERIODS.some(p => p.value === period)) return <Navigate to="/habits/daily" replace />;
  const current = period as HabitFrequency;
  if (isLoading) return <LoadingState label="Iris is counting your streaks…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  const active = data.filter(h => !h.archived);
  const archived = data.filter(h => h.archived);
  const onToggle = (id: string, done: boolean) => toggle.mutate({ id, done });

  return (
    <Page title="Habits" width="wide" description="Tick today. Double-click a day's dot to mark it done; click it once to write that day's note. Click a habit's name for its calendar, where a day can also be marked skipped, and to edit it.">
      {/* A tick that did not reach the server rolls back on screen, which on
          its own looks like a misclick. */}
      {toggle.isError && <p role="alert" className={styles.error}>That tick didn't save. Nothing is lost; try again.</p>}
      <Tabs label="How often" value={current} onChange={v => navigate(`/habits/${v}`)}
        tabs={PERIODS.map(p => ({
          value: p.value,
          label: `${p.label} (${active.filter(h => frequencyOf(h) === p.value).length})`,
        }))}>
        {PERIODS.map(p => (
          <TabPanel key={p.value} value={p.value}>
            <PeriodPanel frequency={p.value} habits={active.filter(h => frequencyOf(h) === p.value)} onToggle={onToggle} />
          </TabPanel>
        ))}
      </Tabs>
      {archived.length > 0 && (
        <details className={styles.archived}>
          <summary>Archived ({archived.length})</summary>
          <ul>
            {archived.map(h => (
              <li key={h.id}><ArchivedHabit h={h} /></li>
            ))}
          </ul>
        </details>
      )}
    </Page>
  );
}

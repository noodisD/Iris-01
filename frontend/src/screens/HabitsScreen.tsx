import React from 'react';
import { useCreateHabit, useHabits, useToggleHabit } from '@/hooks/useHabits';
import { LoadingState, ErrorState } from '@/components/states';
import { color } from '@/components/primitives';
import type { Habit } from '@/types/api';
import { Button, ChoiceGroup, Page, Stat } from '@/ui';
import styles from './HabitsScreen.module.css';

function HabitRow({ h, onToggle }: { h: Habit; onToggle: (id: string, done: boolean) => void }) {
  const c = color(h.color);
  return (
    <article className={styles.row} aria-label={h.name}>
      <div className={styles.what}>
        <button onClick={() => onToggle(h.id, !h.doneToday)} aria-label={`Mark ${h.name} ${h.doneToday ? 'not done' : 'done'}`}
          aria-pressed={h.doneToday} className={styles.tick}
          style={{ borderColor: h.doneToday ? c : undefined, background: h.doneToday ? c : undefined }}>
          {h.doneToday && <span aria-hidden>✓</span>}
        </button>
        <div className={styles.names}>
          <span className={styles.name}>{h.name}</span>
          {h.tag && <span className={styles.tag}>{h.tag}</span>}
          {h.intent && <span className={styles.intent}>{h.intent}</span>}
        </div>
      </div>

      <div className={styles.history} aria-label={`Last ${h.recentDays.length} days: ${h.recentDays.filter(Boolean).length} done`}>
        <div className={styles.dots}>
          {h.recentDays.map((v, i) => (
            <span key={i} className={styles.day} style={v ? { background: c } : undefined} />
          ))}
        </div>
        <div className={styles.axis}><span>{h.recentDays.length} days ago</span><span>Today</span></div>
      </div>

      <div className={styles.streak}>
        <span className={styles.streakNumber} style={{ color: h.streakDays === 0 ? undefined : c }}>{h.streakDays}</span>
        <span className={styles.streakLabel}>day streak, best {h.bestStreak}</span>
      </div>
    </article>
  );
}

/** Constellation view — habits as connected circles. */
function Constellation({ habits, onToggle }: { habits: Habit[]; onToggle: (id: string, done: boolean) => void }) {
  const W = 760, H = 420;
  const positions: Record<string, { x: number; y: number; r: number }> = {};
  habits.forEach((h, i) => {
    const angle = (i / habits.length) * Math.PI * 2 - Math.PI / 2;
    positions[h.id] = { x: W / 2 + Math.cos(angle) * 200, y: H / 2 + Math.sin(angle) * 150, r: 40 + (h.streakDays / 21) * 28 };
  });

  // Arranged in a ring and sized by streak — nothing more. This drew arrows
  // under the heading "how habits pull each other", from a `supports` list the
  // server always sent empty: a causal claim with no data behind it, on a tick
  // list, in a product whose rule is that it does not claim causes.
  return (
    <figure className={styles.constellation}>
      <figcaption className={styles.caption}>Your habits, sized by current streak. Tap one to tick it.</figcaption>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} className={styles.sky} role="img" aria-label="Habits as circles sized by streak">
        {habits.map(h => {
          const p = positions[h.id], c = color(h.color), done = h.doneToday;
          return (
            <g key={h.id} onClick={() => onToggle(h.id, !done)} style={{ cursor: 'pointer' }}>
              <circle cx={p.x} cy={p.y} r={p.r + 8} fill="none" stroke={c} strokeWidth="1" opacity={done ? 0.4 : 0.1} />
              <circle cx={p.x} cy={p.y} r={p.r} fill={done ? c : 'var(--bg-2)'} stroke={c} strokeWidth={done ? 0 : 1.5} opacity={done ? 0.92 : 1} />
              <text x={p.x} y={p.y - 2} textAnchor="middle" fontFamily="var(--font-read)" fontSize="15" fontStyle="italic" fill={done ? 'var(--night)' : 'var(--ink)'}>{h.name.split(' ')[0]}</text>
              <text x={p.x} y={p.y + 14} textAnchor="middle" fontFamily="var(--font-ui)" fontSize="10" fill={done ? 'var(--night)' : 'var(--ink-3)'}>{h.streakDays}d</text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

/** A name, and optionally what it is for. Nothing else is needed to start one. */
function AddHabit() {
  const create = useCreateHabit();
  const [name, setName] = React.useState('');
  const [tag, setTag] = React.useState('');

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    create.mutate({ name: trimmed, tag: tag.trim() || undefined }, {
      onSuccess: () => { setName(''); setTag(''); },
    });
  };

  return (
    <form onSubmit={submit} className={styles.add} aria-label="Add a habit">
      <input aria-label="Habit name" placeholder="A new habit" value={name} onChange={e => setName(e.target.value)} className={styles.nameInput} />
      <input aria-label="Tag" placeholder="Tag (optional)" value={tag} onChange={e => setTag(e.target.value)} className={styles.tagInput} />
      <Button variant="primary" type="submit" disabled={!name.trim() || create.isPending}>Add habit</Button>
      {create.isError && <span role="alert" className={styles.error}>It wasn't saved. Try again.</span>}
    </form>
  );
}

const VIEWS = [{ value: 'list', label: 'List' }, { value: 'constellation', label: 'Constellation' }] as const;

export function HabitsScreen() {
  const { data, isLoading, isError, refetch } = useHabits();
  const toggle = useToggleHabit();
  const [view, setView] = React.useState<'list' | 'constellation'>('list');

  if (isLoading) return <LoadingState label="Iris is counting your streaks…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  const onToggle = (id: string, done: boolean) => toggle.mutate({ id, done });

  return (
    <Page title="Habits" description={`${data.doneCount} of ${data.totalCount} done today.`}
      actions={<ChoiceGroup label="View" options={[...VIEWS]} value={view} onChange={v => v && setView(v)} />}>
      <div className={styles.stats}>
        <Stat value={data.longestActiveStreak} label="Longest active streak, days" />
        <Stat value={`${Math.round(data.consistency30d * 100)}%`} label="Done over the last 30 days" />
      </div>

      {data.suggestion && <p className={styles.suggestion}>{data.suggestion.text}</p>}

      <AddHabit />

      {/* A tick that did not reach the server rolls back on screen, which on
          its own looks like a misclick. */}
      {toggle.isError && <p role="alert" className={styles.error}>That tick didn't save. Nothing is lost; try again.</p>}

      {data.habits.length === 0 ? (
        <p className={styles.empty}>No habits yet. Name one above and tick it off here each day.</p>
      ) : view === 'list' ? (
        <div className={styles.list}>{data.habits.map(h => <HabitRow key={h.id} h={h} onToggle={onToggle} />)}</div>
      ) : (
        <Constellation habits={data.habits} onToggle={onToggle} />
      )}
    </Page>
  );
}

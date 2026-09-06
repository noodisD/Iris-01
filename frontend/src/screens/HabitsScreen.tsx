import React from 'react';
import { useHabits, useToggleHabit } from '@/hooks/useHabits';
import { LoadingState, ErrorState } from '@/components/states';
import { color } from '@/components/primitives';
import type { Habit } from '@/types/api';

function HabitRow({ h, onToggle }: { h: Habit; onToggle: (id: string, done: boolean) => void }) {
  const c = color(h.color);
  return (
    <article style={{ display: 'grid', gridTemplateColumns: '260px 1fr 180px', gap: 24, padding: '20px 0', borderTop: '1px solid var(--line)', alignItems: 'center' }}>
      <div className="col" style={{ gap: 8 }}>
        <div className="row" style={{ alignItems: 'baseline', gap: 10 }}>
          <button onClick={() => onToggle(h.id, !h.doneToday)} aria-label={`Mark ${h.name} ${h.doneToday ? 'not done' : 'done'}`}
            style={{ width: 22, height: 22, borderRadius: '50%', border: `1.5px solid ${h.doneToday ? c : 'var(--line)'}`, background: h.doneToday ? c : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', padding: 0, flexShrink: 0, transition: 'all 0.15s ease' }}>
            {h.doneToday && <span style={{ color: '#14140f', fontSize: 12 }}>✓</span>}
          </button>
          <span className="serif" style={{ fontSize: 24, color: 'var(--ink)' }}>{h.name}</span>
        </div>
        <div style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--mono)', letterSpacing: '0.04em', paddingLeft: 32 }}>{h.tag}</div>
        {h.intent && <div style={{ fontSize: 12, color: 'var(--ink-2)', fontStyle: 'italic', paddingLeft: 32 }}>↳ {h.intent}</div>}
      </div>

      <div className="col" style={{ gap: 6 }}>
        <div className="row" style={{ alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {h.recentDays.map((v, i) => (
            <span key={i} style={{ width: 8, height: 8, borderRadius: '50%', background: v ? c : 'var(--line)', opacity: v ? Math.max(0.45, 1 - (h.recentDays.length - i) / 120) : 1 }} />
          ))}
        </div>
        <div className="row" style={{ justifyContent: 'space-between', fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink-4)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          <span>{h.recentDays.length} days ago</span><span>today</span>
        </div>
      </div>

      <div className="col" style={{ alignItems: 'flex-end', gap: 2 }}>
        <div className="numerals" style={{ fontSize: 56, color: h.streakDays === 0 ? 'var(--ink-3)' : c, lineHeight: 0.85 }}>{h.streakDays}</div>
        <div className="row" style={{ gap: 8, alignItems: 'baseline' }}>
          <span className="kicker">day streak</span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)' }}>best {h.bestStreak}</span>
        </div>
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

  const connections: { from: string; to: string }[] = [];
  habits.forEach(h => h.supports.forEach(to => { if (positions[to]) connections.push({ from: h.id, to }); }));

  return (
    <div style={{ padding: '20px 0' }}>
      <div className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12 }}>
        <div className="kicker">your constellation · how habits pull each other</div>
        <div style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>arrows: doing → supports → doing</div>
      </div>
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} style={{ maxWidth: W }}>
        <defs>
          <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M 0 2 L 9 5 L 0 8 z" fill="var(--sage)" opacity="0.7" />
          </marker>
        </defs>
        {connections.map((cn, i) => {
          const f = positions[cn.from], t = positions[cn.to];
          const dx = t.x - f.x, dy = t.y - f.y, dist = Math.hypot(dx, dy);
          const ux = dx / dist, uy = dy / dist;
          return <line key={i} x1={f.x + ux * f.r} y1={f.y + uy * f.r} x2={t.x - ux * (t.r + 6)} y2={t.y - uy * (t.r + 6)} stroke="var(--sage)" strokeWidth="1" strokeDasharray="3 4" opacity="0.5" markerEnd="url(#arr)" />;
        })}
        {habits.map(h => {
          const p = positions[h.id], c = color(h.color), done = h.doneToday;
          return (
            <g key={h.id} onClick={() => onToggle(h.id, !done)} style={{ cursor: 'pointer' }}>
              <circle cx={p.x} cy={p.y} r={p.r + 8} fill="none" stroke={c} strokeWidth="1" opacity={done ? 0.4 : 0.1} />
              <circle cx={p.x} cy={p.y} r={p.r} fill={done ? c : 'var(--bg-2)'} stroke={c} strokeWidth={done ? 0 : 1.5} opacity={done ? 0.92 : 1} />
              <text x={p.x} y={p.y - 2} textAnchor="middle" fontFamily="var(--serif)" fontSize="15" fontStyle="italic" fill={done ? '#14140f' : 'var(--ink)'}>{h.name.split(' ')[0]}</text>
              <text x={p.x} y={p.y + 14} textAnchor="middle" fontFamily="var(--mono)" fontSize="10" fill={done ? '#14140f' : 'var(--ink-3)'}>{h.streakDays}d</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function HabitsScreen() {
  const { data, isLoading, isError, refetch } = useHabits();
  const toggle = useToggleHabit();
  const [view, setView] = React.useState<'list' | 'constellation'>('list');

  if (isLoading) return <LoadingState label="Iris is counting your streaks…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  const onToggle = (id: string, done: boolean) => toggle.mutate({ id, done });

  return (
    <div className="col" style={{ padding: '32px 56px 48px', gap: 28 }}>
      <header className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid var(--line)', paddingBottom: 18 }}>
        <div className="col" style={{ gap: 6 }}>
          <div className="kicker">habits · daily practice</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
            {data.doneCount}<span style={{ color: 'var(--ink-3)', fontStyle: 'italic' }}>/{data.totalCount}</span> today.
          </h1>
        </div>
        <div className="row" style={{ gap: 24, alignItems: 'baseline' }}>
          <div className="col" style={{ gap: 2, alignItems: 'flex-end' }}>
            <span className="numerals" style={{ fontSize: 28, color: 'var(--sage)' }}>{data.longestActiveStreak}</span>
            <span className="kicker">longest active</span>
          </div>
          <div className="col" style={{ gap: 2, alignItems: 'flex-end' }}>
            <span className="numerals" style={{ fontSize: 28, color: 'var(--ink)' }}>{Math.round(data.consistency30d * 100)}<span style={{ fontSize: 14, color: 'var(--ink-3)' }}>%</span></span>
            <span className="kicker">30d consistency</span>
          </div>
          <div className="row" style={{ background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 999, padding: 2 }}>
            {(['list', 'constellation'] as const).map(v => (
              <button key={v} onClick={() => setView(v)} style={{ padding: '6px 14px', borderRadius: 999, border: 'none', cursor: 'pointer', background: view === v ? 'var(--sage)' : 'transparent', color: view === v ? '#14140f' : 'var(--ink-3)', fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase' }}>{v}</button>
            ))}
          </div>
        </div>
      </header>

      {data.suggestion && (
        <div className="row" style={{ gap: 14, alignItems: 'flex-start', padding: '4px 0' }}>
          <div className="iris-orb sm" style={{ marginTop: 6 }} />
          <div className="serif ital" style={{ fontSize: 20, lineHeight: 1.4, color: 'var(--ink)', maxWidth: 760 }}>
            "{data.suggestion.text}"
          </div>
        </div>
      )}

      {view === 'list' ? (
        <div>
          {data.habits.map(h => <HabitRow key={h.id} h={h} onToggle={onToggle} />)}
          <hr style={{ border: 0, borderTop: '1px solid var(--line)', margin: 0 }} />
        </div>
      ) : (
        <Constellation habits={data.habits} onToggle={onToggle} />
      )}
    </div>
  );
}

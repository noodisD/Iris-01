// screens/habits.jsx — interactive checkboxes, list + constellation views

const INITIAL_HABITS = [
  { id: 'meditate', name: 'Meditate', tag: '10 min · morning', streak: 14, best: 23, doneToday: true,
    color: 'var(--sage)', days: 60, dotsSeed: 7, intent: 'be less reactive at standup',
    supports: ['walk'], supportedBy: [] },
  { id: 'walk', name: 'Walk outside', tag: 'noon or after work', streak: 9, best: 16, doneToday: true,
    color: 'var(--amber)', days: 60, dotsSeed: 13, intent: 'reset between focus blocks',
    supports: ['phonebed'], supportedBy: ['meditate'] },
  { id: 'read', name: 'Read · paper', tag: '20 pages · before bed', streak: 4, best: 22, doneToday: false,
    color: 'var(--indigo)', days: 60, dotsSeed: 19, intent: "keep a mind that isn't a feed",
    supports: ['phonebed'], supportedBy: [] },
  { id: 'water', name: 'Water early', tag: 'before coffee', streak: 21, best: 21, doneToday: true,
    color: 'var(--sage)', days: 60, dotsSeed: 23, intent: 'morning headaches',
    supports: [], supportedBy: [] },
  { id: 'phonebed', name: 'No phone in bed', tag: 'after 10pm', streak: 0, best: 5, doneToday: false,
    color: 'var(--rose)', days: 60, dotsSeed: 5, intent: 'fall asleep before midnight',
    supports: [], supportedBy: ['walk', 'read'] },
];

function makeDots(seed, days) {
  let s = seed;
  return Array.from({ length: days }, (_, i) => {
    s = (s * 9301 + 49297) % 233280;
    const base = s / 233280;
    const recency = 1 - (i / days) * 0.4;
    return base * recency > 0.45 ? 1 : 0;
  });
}

function HabitRow({ h, onToggle }) {
  const dots = makeDots(h.dotsSeed, h.days);
  return (
    <article style={{
      display: 'grid', gridTemplateColumns: '260px 1fr 180px',
      gap: 24, padding: '20px 0', borderTop: '1px solid var(--line)', alignItems: 'center',
    }}>
      <div className="col" style={{ gap: 8 }}>
        <div className="row" style={{ alignItems: 'baseline', gap: 10 }}>
          <button onClick={() => onToggle(h.id)} aria-label={`Mark ${h.name} done`} style={{
            width: 22, height: 22, borderRadius: '50%',
            border: '1.5px solid ' + (h.doneToday ? h.color : 'var(--line)'),
            background: h.doneToday ? h.color : 'transparent',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', padding: 0, flexShrink: 0,
            transition: 'all 0.15s ease',
          }}>
            {h.doneToday && <span style={{ color: '#14140f', fontSize: 12 }}>✓</span>}
          </button>
          <span className="serif" style={{ fontSize: 24, color: 'var(--ink)', textDecoration: h.doneToday ? 'none' : 'none' }}>{h.name}</span>
        </div>
        <div style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--mono)', letterSpacing: '0.04em', paddingLeft: 32 }}>{h.tag}</div>
        <div style={{ fontSize: 12, color: 'var(--ink-2)', fontStyle: 'italic', paddingLeft: 32 }}>↳ {h.intent}</div>
      </div>

      <div className="col" style={{ gap: 6 }}>
        <div className="row" style={{ alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {dots.map((v, i) => (
            <span key={i} style={{
              width: 8, height: 8, borderRadius: '50%',
              background: v ? h.color : 'var(--line)',
              opacity: v ? Math.max(0.45, 1 - (dots.length - i) / 120) : 1,
            }} />
          ))}
        </div>
        <div className="row" style={{ justifyContent: 'space-between', fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink-4)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          <span>60 days ago</span><span>today</span>
        </div>
      </div>

      <div className="col" style={{ alignItems: 'flex-end', gap: 2 }}>
        <div className="numerals" style={{ fontSize: 56, color: h.streak === 0 ? 'var(--ink-3)' : h.color, lineHeight: 0.85 }}>{h.streak}</div>
        <div className="row" style={{ gap: 8, alignItems: 'baseline' }}>
          <span className="kicker">day streak</span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)' }}>best {h.best}</span>
        </div>
      </div>
    </article>
  );
}

/* Constellation view — habits as connected circles. Hand-positioned. */
function HabitsConstellation({ habits, onToggle }) {
  // Position each habit on a circular layout
  const W = 760, H = 460;
  const positions = {
    meditate: { x: 380, y: 90,  r: 64 },
    walk:     { x: 580, y: 230, r: 52 },
    read:     { x: 380, y: 370, r: 48 },
    water:    { x: 180, y: 230, r: 70 },
    phonebed: { x: 480, y: 330, r: 40 },
  };
  // Connections: source -> target
  const connections = [];
  habits.forEach(h => {
    h.supports.forEach(target => {
      connections.push({ from: h.id, to: target, color: h.color });
    });
  });

  return (
    <div style={{ position: 'relative', padding: '20px 0' }}>
      <div className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12 }}>
        <div className="kicker">your constellation · how habits pull each other</div>
        <div style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>arrows show: doing → supports → doing</div>
      </div>

      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} style={{ maxWidth: W }}>
        <defs>
          <radialGradient id="con-bg" cx="50%" cy="50%" r="60%">
            <stop offset="0%" stopColor="rgba(169,200,163,0.04)" />
            <stop offset="100%" stopColor="transparent" />
          </radialGradient>
          <marker id="arrow-sage" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M 0 2 L 9 5 L 0 8 z" fill="var(--sage)" opacity="0.7" />
          </marker>
        </defs>
        <rect x="0" y="0" width={W} height={H} fill="url(#con-bg)" />

        {/* tiny stars/dots for atmosphere */}
        {Array.from({ length: 28 }).map((_, i) => {
          const x = (i * 137) % W;
          const y = (i * 211) % H;
          return <circle key={i} cx={x} cy={y} r="0.8" fill="var(--ink-4)" opacity={(i % 5) / 8} />;
        })}

        {/* Connections */}
        {connections.map((c, i) => {
          const f = positions[c.from], t = positions[c.to];
          if (!f || !t) return null;
          const dx = t.x - f.x, dy = t.y - f.y;
          const dist = Math.sqrt(dx*dx + dy*dy);
          const ux = dx / dist, uy = dy / dist;
          const x1 = f.x + ux * f.r;
          const y1 = f.y + uy * f.r;
          const x2 = t.x - ux * (t.r + 6);
          const y2 = t.y - uy * (t.r + 6);
          return (
            <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
              stroke="var(--sage)" strokeWidth="1" strokeDasharray="3 4" opacity="0.5"
              markerEnd="url(#arrow-sage)" />
          );
        })}

        {/* Habits */}
        {habits.map(h => {
          const p = positions[h.id];
          if (!p) return null;
          const isDone = h.doneToday;
          return (
            <g key={h.id} onClick={() => onToggle(h.id)} style={{ cursor: 'pointer' }}>
              <circle cx={p.x} cy={p.y} r={p.r + 8} fill="none" stroke={h.color} strokeWidth="1" opacity={isDone ? 0.4 : 0.1} />
              <circle cx={p.x} cy={p.y} r={p.r} fill={isDone ? h.color : 'var(--bg-2)'} stroke={h.color} strokeWidth={isDone ? 0 : 1.5} opacity={isDone ? 0.92 : 1} />
              <text x={p.x} y={p.y - 4} textAnchor="middle" fontFamily="var(--serif)" fontSize="16" fontStyle="italic"
                fill={isDone ? '#14140f' : 'var(--ink)'}>
                {h.name.split(' ')[0]}
              </text>
              <text x={p.x} y={p.y + 14} textAnchor="middle" fontFamily="var(--mono)" fontSize="10" letterSpacing="0.05em"
                fill={isDone ? '#14140f' : 'var(--ink-3)'} opacity="0.9">
                {h.streak}d
              </text>
              <text x={p.x} y={p.y + p.r + 18} textAnchor="middle" fontFamily="var(--mono)" fontSize="9" letterSpacing="0.1em" textTransform="uppercase"
                fill="var(--ink-4)">
                {isDone ? '● DONE' : '○ open'}
              </text>
            </g>
          );
        })}

        {/* Legend / Iris note */}
        <text x="20" y={H - 26} fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)" letterSpacing="0.08em">CONSTELLATION · KIN: SUPPORTS · TAP TO MARK DONE</text>
      </svg>

      {/* Constellation insight strip */}
      <div className="row" style={{ gap: 14, padding: '14px 18px', background: 'var(--bg-2)', border: '1px solid var(--line-soft)', borderRadius: 10, marginTop: 10 }}>
        <div className="iris-orb sm" style={{ marginTop: 4 }} />
        <div className="col" style={{ gap: 4 }}>
          <span className="kicker">iris sees the shape</span>
          <span className="serif ital" style={{ fontSize: 18, color: 'var(--ink)', lineHeight: 1.4, maxWidth: 720 }}>
            "Walk and Read are both upstream of No-phone-in-bed — when either lands, you sleep better. Meditate quietly props up Walk. Water sits alone — it just works."
          </span>
        </div>
      </div>
    </div>
  );
}

function HabitsScreen() {
  const [habits, setHabits] = React.useState(INITIAL_HABITS);
  const [view, setView] = React.useState('list');

  const toggle = (id) => {
    setHabits(prev => prev.map(h => h.id === id ? {
      ...h,
      doneToday: !h.doneToday,
      streak: !h.doneToday ? h.streak + 1 : Math.max(0, h.streak - 1),
    } : h));
  };

  const doneCount = habits.filter(h => h.doneToday).length;
  const longest = habits.reduce((m, h) => Math.max(m, h.streak), 0);

  return (
    <div className="col" style={{ padding: '32px 56px 48px', gap: 28 }}>
      <header className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid var(--line)', paddingBottom: 18 }}>
        <div className="col" style={{ gap: 6 }}>
          <div className="kicker">habits · daily practice</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
            {doneCount}<span style={{ color: 'var(--ink-3)', fontStyle: 'italic' }}>/{habits.length}</span> today.
          </h1>
        </div>
        <div className="row" style={{ gap: 24, alignItems: 'baseline' }}>
          <div className="col" style={{ gap: 2, alignItems: 'flex-end' }}>
            <span className="numerals" style={{ fontSize: 28, color: 'var(--sage)' }}>{longest}</span>
            <span className="kicker">longest active</span>
          </div>
          <div className="col" style={{ gap: 2, alignItems: 'flex-end' }}>
            <span className="numerals" style={{ fontSize: 28, color: 'var(--ink)' }}>67<span style={{ fontSize: 14, color: 'var(--ink-3)', letterSpacing: '0.06em' }}>%</span></span>
            <span className="kicker">30d consistency</span>
          </div>
          {/* View toggle */}
          <div className="row" style={{ background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 999, padding: 2 }}>
            {['list','constellation'].map(v => (
              <button key={v} onClick={() => setView(v)} style={{
                padding: '6px 14px', borderRadius: 999, border: 'none', cursor: 'pointer',
                background: view === v ? 'var(--sage)' : 'transparent',
                color: view === v ? '#14140f' : 'var(--ink-3)',
                fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase',
              }}>{v}</button>
            ))}
          </div>
          <button className="btn primary">+ new habit</button>
        </div>
      </header>

      <div className="row" style={{ gap: 14, alignItems: 'flex-start', padding: '4px 0' }}>
        <div className="iris-orb sm" style={{ marginTop: 6 }} />
        <div className="serif ital" style={{ fontSize: 20, lineHeight: 1.4, color: 'var(--ink)', maxWidth: 760 }}>
          "Your 'no phone in bed' streak broke twice this month — both times the night after a 9pm work message. Want me to mute slack at 9 on weekdays?"
          <button className="btn" style={{ marginLeft: 16, fontSize: 11, padding: '4px 10px', color: 'var(--sage)', borderColor: 'var(--sage-dim)' }}>try it</button>
        </div>
      </div>

      {view === 'list' ? (
        <div>
          {habits.map(h => <HabitRow key={h.id} h={h} onToggle={toggle} />)}
          <hr style={{ border: 0, borderTop: '1px solid var(--line)', margin: 0 }} />
        </div>
      ) : (
        <HabitsConstellation habits={habits} onToggle={toggle} />
      )}

      <div style={{ padding: '20px 24px', border: '1px dashed var(--line)', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div className="col" style={{ gap: 4 }}>
          <span className="kicker">iris suggests</span>
          <div className="serif" style={{ fontSize: 18, color: 'var(--ink)' }}>
            <span style={{ fontStyle: 'italic' }}>Stretch · 5 min after coffee.</span>
            <span style={{ color: 'var(--ink-3)', fontSize: 13, fontFamily: 'var(--sans)', fontStyle: 'normal', marginLeft: 12 }}>You mentioned tight hips 4 times in the last 2 weeks.</span>
          </div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn">not now</button>
          <button className="btn primary">add to today</button>
        </div>
      </div>
    </div>
  );
}

window.HabitsScreen = HabitsScreen;

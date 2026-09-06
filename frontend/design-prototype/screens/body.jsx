// screens/body.jsx — "Body" — Fitbit Air signals interpreted by Iris

// ── Generated body data ──
const mkBodySeries = (n, base, amp, seed) => {
  let s = seed;
  return Array.from({ length: n }, (_, i) => {
    s = (s * 9301 + 49297) % 233280;
    const r = s / 233280;
    return base + Math.sin(i / 2.3) * amp * 0.4 + (r - 0.5) * amp * 0.8;
  });
};

const BODY = {
  hrv14:   mkBodySeries(14, 48, 12, 41), // ms
  rhr14:   mkBodySeries(14, 58, 5,  73), // bpm
  brth14:  mkBodySeries(14, 14.6, 1.4, 19), // br/min
  temp14:  mkBodySeries(14, 0.0, 0.45, 29), // delta °F
  readiness14: mkBodySeries(14, 68, 14, 53).map(v => Math.max(20, Math.min(98, Math.round(v)))),
};

// Sleep stages last night — minutes
const SLEEP_STAGES = [
  { stage: 'awake',  mins: 23,  color: 'var(--rose)'    },
  { stage: 'rem',    mins: 78,  color: 'var(--indigo)'  },
  { stage: 'light',  mins: 188, color: 'rgba(154,163,212,0.55)' },
  { stage: 'deep',   mins: 122, color: 'var(--sage)'    },
];

// Hypnogram-ish 8h timeline of stages (28 segments of ~17min each)
const HYPNO = [
  'awake','light','light','rem','light','deep','deep','deep','light','rem','rem','light',
  'deep','deep','light','rem','rem','light','light','deep','rem','rem','light','light','awake','rem','light','awake'
];
const HYPNO_Y = { awake: 0, rem: 1, light: 2, deep: 3 };
const HYPNO_COLOR = { awake: 'var(--rose)', rem: 'var(--indigo)', light: 'rgba(154,163,212,0.55)', deep: 'var(--sage)' };

function FitbitAirPebble() {
  // A tiny abstract pebble — not Fitbit branded UI, just a stylized representation.
  return (
    <svg width="68" height="40" viewBox="0 0 68 40">
      <defs>
        <radialGradient id="pebble" cx="40%" cy="35%" r="60%">
          <stop offset="0%" stopColor="#2a2a22" />
          <stop offset="60%" stopColor="#1a1a14" />
          <stop offset="100%" stopColor="#0d0d0a" />
        </radialGradient>
      </defs>
      <rect x="0" y="0" width="68" height="40" rx="20" fill="url(#pebble)" stroke="var(--line)" />
      <circle cx="34" cy="20" r="3" fill="var(--sage)" opacity="0.85" style={{ filter: 'drop-shadow(0 0 4px var(--sage))' }} />
      <circle cx="34" cy="20" r="1.4" fill="#0a0a06" />
    </svg>
  );
}

function HypnogramSVG() {
  // 28 segments, each draws a vertical bar at its stage row + a connecting line
  const w = 720, h = 110;
  const segW = w / HYPNO.length;
  const rowH = h / 4;
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`}>
      {/* row guidelines */}
      {[0,1,2,3].map(r => (
        <line key={r} x1="40" y1={r * rowH + rowH/2} x2={w} y2={r * rowH + rowH/2} stroke="var(--line-soft)" />
      ))}
      {/* row labels */}
      {['awake','rem','light','deep'].map((label, r) => (
        <text key={label} x="0" y={r * rowH + rowH/2 + 4} fontFamily="var(--mono)" fontSize="9" fill="var(--ink-3)" letterSpacing="0.08em">
          {label}
        </text>
      ))}
      {/* segments */}
      {HYPNO.map((stage, i) => {
        const y = HYPNO_Y[stage] * rowH + rowH/2 - 4;
        const x = 40 + i * (segW * (w - 40) / w);
        const segWidth = (w - 40) / HYPNO.length;
        return (
          <rect key={i} x={x} y={y} width={segWidth - 1} height={8} rx="1.5" fill={HYPNO_COLOR[stage]} />
        );
      })}
      {/* time labels */}
      <text x="40" y={h - 2} fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)" letterSpacing="0.08em">11:14p</text>
      <text x={w/2} y={h - 2} textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)" letterSpacing="0.08em">3:00a</text>
      <text x={w - 2} y={h - 2} textAnchor="end" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)" letterSpacing="0.08em">6:51a</text>
    </svg>
  );
}

function BodyCard({ kicker, span = 1, children, footer = null }) {
  return (
    <div style={{
      gridColumn: `span ${span}`,
      background: 'var(--bg-2)',
      border: '1px solid var(--line-soft)',
      borderRadius: 10,
      padding: '18px 20px',
      display: 'flex', flexDirection: 'column', gap: 10,
      minHeight: 140,
    }}>
      <div className="kicker">{kicker}</div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>{children}</div>
      {footer && (
        <div className="row" style={{ justifyContent: 'space-between', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          {footer}
        </div>
      )}
    </div>
  );
}

function BodyScreen() {
  const totalSleep = SLEEP_STAGES.reduce((a, b) => a + b.mins, 0);
  const readinessToday = BODY.readiness14[13];

  return (
    <div className="col" style={{ padding: '24px 32px 40px', gap: 24 }}>
      {/* Masthead */}
      <header className="row" style={{ alignItems: 'flex-end', justifyContent: 'space-between', borderBottom: '1px solid var(--line)', paddingBottom: 16 }}>
        <div className="col" style={{ gap: 6 }}>
          <div className="kicker">body · what the air heard</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 56, letterSpacing: '-0.025em', lineHeight: 1 }}>
            Your body, in <span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>signals</span>.
          </h1>
        </div>
        <div className="row" style={{ gap: 14, alignItems: 'center' }}>
          <FitbitAirPebble />
          <div className="col" style={{ gap: 2 }}>
            <span style={{ fontSize: 13, color: 'var(--ink)' }}>Fitbit Air</span>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--sage)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>● synced · 4 min ago</span>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)' }}>battery 71% · 5d left</span>
          </div>
          <button className="btn">manage</button>
        </div>
      </header>

      {/* Hero — body said / you said */}
      <section style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 32, padding: '8px 0 16px' }}>
        <div className="col" style={{ gap: 8 }}>
          <div className="kicker">today's readiness</div>
          <div className="row" style={{ gap: 24, alignItems: 'flex-end' }}>
            <div className="numerals" style={{ fontSize: 168, color: readinessToday > 70 ? 'var(--sage)' : readinessToday > 40 ? 'var(--amber)' : 'var(--rose)', letterSpacing: '-0.04em', lineHeight: 0.82 }}>
              {readinessToday}
            </div>
            <div className="col" style={{ gap: 4, paddingBottom: 18 }}>
              <span className="kicker">/ 100</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-3)' }}>Δ {readinessToday - BODY.readiness14[12] > 0 ? '+' : ''}{readinessToday - BODY.readiness14[12]} vs yesterday</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-3)' }}>14-day avg · 67</span>
            </div>
          </div>
          <Sparkline data={BODY.readiness14} w={460} h={36} stroke="var(--sage)" baseline />
          <div className="row" style={{ gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
            <span className="tag">HRV ↑</span>
            <span className="tag">deep sleep ↑12m</span>
            <span className="tag" style={{ color: 'var(--rose)', borderColor: 'var(--rose)' }}>RHR ↑3 bpm</span>
            <span className="tag">cardio load · low</span>
          </div>
        </div>

        {/* Iris's translation */}
        <div className="col" style={{ gap: 14, paddingLeft: 32, borderLeft: '1px dashed var(--line)' }}>
          <div className="row" style={{ gap: 10, alignItems: 'center' }}>
            <div className="iris-orb sm" />
            <span className="kicker">iris translates</span>
          </div>
          <div className="serif ital" style={{ fontSize: 22, lineHeight: 1.4, color: 'var(--ink)' }}>
            "Your body slept better than you felt. HRV recovered, deep sleep grew — but resting heart rate is still warm from yesterday. The Air says you're 72% loaded; your words say 38."
          </div>
          <hr className="dotline" />
          <div className="col" style={{ gap: 8 }}>
            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>body says</span>
              <span className="serif" style={{ fontSize: 22, color: 'var(--sage)' }}>72</span>
            </div>
            <div style={{ height: 1, background: 'var(--line-soft)' }} />
            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>your words say</span>
              <span className="serif" style={{ fontSize: 22, color: 'var(--amber)' }}>38</span>
            </div>
            <div style={{ height: 1, background: 'var(--line-soft)' }} />
            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>gap — both true</span>
              <span className="serif" style={{ fontSize: 22, color: 'var(--ink)' }}>34</span>
            </div>
          </div>
        </div>
      </section>

      {/* Detail grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: 14 }}>
        {/* HRV */}
        <BodyCard kicker="HRV · 14 nights" span={4} footer={[<span key="a">avg 48 ms · +5 vs prev wk</span>, <span key="b">last night 54</span>]}>
          <div className="row" style={{ gap: 10, alignItems: 'baseline' }}>
            <div className="numerals" style={{ fontSize: 56, color: 'var(--sage)' }}>54<span style={{ fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--ink-3)', letterSpacing: '0.06em', marginLeft: 6 }}>MS</span></div>
            <div className="col" style={{ gap: 2 }}>
              <span style={{ fontSize: 11, color: 'var(--sage)', fontFamily: 'var(--mono)' }}>↑ 12% vs baseline</span>
              <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>nervous system, calmer</span>
            </div>
          </div>
          <Sparkline data={BODY.hrv14} w={380} h={44} stroke="var(--sage)" fill dots />
        </BodyCard>

        {/* Resting HR */}
        <BodyCard kicker="Resting HR · 14d" span={4} footer={[<span key="a">avg 58 bpm</span>, <span key="b">elevated after late slack msg</span>]}>
          <div className="row" style={{ gap: 10, alignItems: 'baseline' }}>
            <div className="numerals" style={{ fontSize: 56, color: 'var(--rose)' }}>61<span style={{ fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--ink-3)', letterSpacing: '0.06em', marginLeft: 6 }}>BPM</span></div>
            <div className="col" style={{ gap: 2 }}>
              <span style={{ fontSize: 11, color: 'var(--rose)', fontFamily: 'var(--mono)' }}>↑ 3 vs typical</span>
              <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>still cooling from yesterday</span>
            </div>
          </div>
          <Sparkline data={BODY.rhr14} w={380} h={44} stroke="var(--rose)" />
        </BodyCard>

        {/* Breathing rate */}
        <BodyCard kicker="Breath · while asleep" span={4} footer={[<span key="a">14.2 br/min</span>, <span key="b">steady · no apnea flags</span>]}>
          <div className="row" style={{ gap: 10, alignItems: 'baseline' }}>
            <div className="numerals" style={{ fontSize: 56, color: 'var(--indigo)' }}>14.2<span style={{ fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--ink-3)', letterSpacing: '0.06em', marginLeft: 6 }}>BR/M</span></div>
            <div className="col" style={{ gap: 2 }}>
              <span style={{ fontSize: 11, color: 'var(--indigo)', fontFamily: 'var(--mono)' }}>variance · low</span>
              <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>quieter than monday</span>
            </div>
          </div>
          <Sparkline data={BODY.brth14} w={380} h={44} stroke="var(--indigo)" />
        </BodyCard>

        {/* Hypnogram */}
        <BodyCard kicker="Last night · 6h 51m"
          span={8}
          footer={[<span key="a">22% deep · target 20%</span>, <span key="b">19% rem · target 22%</span>, <span key="c">3 awakenings</span>, <span key="d">smart wake @ 6:51</span>]}>
          <div style={{ width: '100%' }}>
            <HypnogramSVG />
          </div>
        </BodyCard>

        {/* Stage donut */}
        <BodyCard kicker="Sleep stages" span={4}>
          <div className="row" style={{ gap: 14, alignItems: 'center', height: '100%' }}>
            <svg width="120" height="120" viewBox="0 0 120 120">
              {(() => {
                let off = 0;
                const C = 2 * Math.PI * 50;
                return SLEEP_STAGES.map((s, i) => {
                  const frac = s.mins / totalSleep;
                  const len = frac * C;
                  const el = (
                    <circle key={i} cx="60" cy="60" r="50" fill="none"
                      stroke={s.color} strokeWidth="14"
                      strokeDasharray={`${len} ${C}`}
                      strokeDashoffset={-off}
                      transform="rotate(-90 60 60)" />
                  );
                  off += len;
                  return el;
                });
              })()}
              <text x="60" y="58" textAnchor="middle" fontFamily="var(--serif)" fontSize="28" fill="var(--ink)">6h 51m</text>
              <text x="60" y="76" textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-3)" letterSpacing="0.1em">SLEPT</text>
            </svg>
            <div className="col" style={{ gap: 6, flex: 1 }}>
              {SLEEP_STAGES.map(s => (
                <div key={s.stage} className="row" style={{ alignItems: 'baseline', gap: 8 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: s.color, flexShrink: 0 }} />
                  <span style={{ flex: 1, fontSize: 12, color: 'var(--ink-2)' }}>{s.stage}</span>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink)' }}>{Math.floor(s.mins/60)}h {s.mins%60}m</span>
                </div>
              ))}
            </div>
          </div>
        </BodyCard>

        {/* HRV vs anxiety overlay — the fusion chart */}
        <BodyCard kicker="HRV ↔ self-reported anxiety · 14d" span={8}
          footer={[<span key="a">r = −0.68 · strong inverse</span>, <span key="b">when HRV drops 10ms, anxiety self-report climbs 1.4 pts within 36h</span>]}>
          <svg width="100%" height="160" viewBox="0 0 720 160" preserveAspectRatio="none">
            {/* baseline */}
            <line x1="0" y1="80" x2="720" y2="80" stroke="var(--line)" strokeDasharray="2 4" />
            {/* hrv line (top) */}
            {(() => {
              const min = Math.min(...BODY.hrv14), max = Math.max(...BODY.hrv14);
              const path = BODY.hrv14.map((v, i) => {
                const x = (i / (BODY.hrv14.length - 1)) * 720;
                const y = 70 - ((v - min) / (max - min)) * 60;
                return `${i ? 'L' : 'M'} ${x} ${y}`;
              }).join(' ');
              return <path d={path} stroke="var(--sage)" strokeWidth="1.6" fill="none" />;
            })()}
            {/* anxiety bars (bottom, mirrored) */}
            {(() => {
              const anx = [6,7,5,8,9,7,5,4,6,7,8,6,5,4]; // 0-10
              return anx.map((a, i) => {
                const x = (i / 13) * 720;
                const h = (a / 10) * 60;
                return <rect key={i} x={x - 4} y={90} width="8" height={h} rx="1.5" fill="var(--rose)" opacity={0.4 + a/25} />;
              });
            })()}
            {/* labels */}
            <text x="6" y="14" fontFamily="var(--mono)" fontSize="9" fill="var(--sage)" letterSpacing="0.08em">HRV · MS</text>
            <text x="6" y="156" fontFamily="var(--mono)" fontSize="9" fill="var(--rose)" letterSpacing="0.08em">ANXIETY · /10</text>
          </svg>
        </BodyCard>

        {/* Skin temp */}
        <BodyCard kicker="Skin temp · variation" span={4}
          footer={[<span key="a">avg Δ +0.1°F</span>, <span key="b">spike thu — illness or cycle?</span>]}>
          <div className="row" style={{ gap: 10, alignItems: 'baseline' }}>
            <div className="numerals" style={{ fontSize: 44, color: 'var(--amber)' }}>+0.3<span style={{ fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--ink-3)', letterSpacing: '0.06em', marginLeft: 6 }}>°F</span></div>
            <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>vs your baseline</span>
          </div>
          {/* ribbon */}
          <svg width="100%" height="50" viewBox="0 0 280 50">
            <line x1="0" y1="25" x2="280" y2="25" stroke="var(--line)" strokeDasharray="2 3" />
            {BODY.temp14.map((t, i) => {
              const x = (i / 13) * 280;
              const y = 25 - t * 30;
              return <circle key={i} cx={x} cy={y} r="3" fill={t > 0.3 ? 'var(--amber)' : t < -0.2 ? 'var(--indigo)' : 'var(--ink-3)'} />;
            })}
          </svg>
        </BodyCard>

        {/* Cardio load */}
        <BodyCard kicker="Cardio load · 7d" span={4}
          footer={[<span key="a">today · 14</span>, <span key="b">target 18–24</span>]}>
          <div className="row" style={{ gap: 10, alignItems: 'baseline' }}>
            <div className="numerals" style={{ fontSize: 56, color: 'var(--ink)' }}>14</div>
            <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>undertrained · room to move</span>
          </div>
          <BarSeries data={[18,22,11,16,8,28,14]} w={280} h={48} color={(d) => d > 24 ? 'var(--rose)' : d < 12 ? 'var(--ink-4)' : 'var(--sage)'} />
          <div className="row" style={{ justifyContent: 'space-between', fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink-4)', letterSpacing: '0.08em' }}>
            {['m','t','w','t','f','s','s'].map((d, i) => <span key={i}>{d}</span>)}
          </div>
        </BodyCard>

        {/* AFib watch — quiet, reassuring */}
        <BodyCard kicker="Heart rhythm · background" span={4}
          footer={[<span key="a">checked 47 nights</span>, <span key="b">last check · 04:18 am</span>]}>
          <div className="row" style={{ alignItems: 'center', gap: 14 }}>
            <svg width="64" height="44" viewBox="0 0 64 44">
              <polyline points="0,22 10,22 14,8 18,38 22,22 30,22 34,12 38,30 42,22 64,22" stroke="var(--sage)" strokeWidth="1.4" fill="none" />
            </svg>
            <div className="col" style={{ gap: 2 }}>
              <span className="serif" style={{ fontSize: 22, color: 'var(--ink)' }}>Steady.</span>
              <span style={{ fontSize: 11, color: 'var(--sage)', fontFamily: 'var(--mono)' }}>no AFib flags</span>
            </div>
          </div>
        </BodyCard>
      </div>

      {/* Bottom narrative — Iris knits it together */}
      <section className="row" style={{ gap: 24, padding: '20px 24px', background: 'var(--bg-2)', border: '1px solid var(--line-soft)', borderRadius: 10 }}>
        <div className="iris-orb" style={{ marginTop: 4 }} />
        <div className="col" style={{ gap: 10, flex: 1 }}>
          <div className="kicker">iris, reading body + words together</div>
          <div className="serif" style={{ fontSize: 20, lineHeight: 1.45, color: 'var(--ink)', maxWidth: 920 }}>
            "Across the last two weeks, your <span style={{ color: 'var(--sage)' }}>HRV climbs the day after a real lunch and a slow morning</span> — and dips the night after a late Slack message. Sleep depth has grown back. <span style={{ fontStyle: 'italic' }}>Your body is forgiving you for the standup, faster than you are.</span>"
          </div>
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            <button className="btn" style={{ color: 'var(--sage)', borderColor: 'var(--sage-dim)' }}>↗ see the correlation</button>
            <button className="btn">ask iris about this</button>
          </div>
        </div>
      </section>

      <div className="row" style={{ justifyContent: 'space-between', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.06em', textTransform: 'uppercase', paddingTop: 4 }}>
        <span>fitbit air · 12g · paired apr 14, 2026</span>
        <span>raw data stays on-device · iris reads summaries only</span>
      </div>
    </div>
  );
}

window.BodyScreen = BodyScreen;

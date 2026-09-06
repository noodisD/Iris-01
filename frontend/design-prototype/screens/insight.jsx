// screens/insight.jsx — Insights index + two deep-dive variants

const ALL_INSIGHTS = [
  {
    id: 'body-words',
    featured: true,
    kicker: 'fusion pattern',
    headlineFrag1: 'Your body forgives you',
    headlineFrag2: 'faster than',
    headlineFrag3: 'you forgive yourself.',
    summary: 'On 9 of the last 11 days you scored your day a 4–6 — while your overnight HRV climbed back to baseline within hours of the stressor ending.',
    age: 'new today',
    tags: ['fusion · air + journal', 'high confidence', '11 supporting nights'],
    confidence: 0.91,
    color: 'sage',
  },
  {
    id: 'monday',
    kicker: 'temporal pattern',
    headlineFrag1: 'You are',
    headlineFrag2: '32% more anxious',
    headlineFrag3: 'on Mondays.',
    summary: 'Anxiety climbs 32% Monday mornings vs. other weekday mornings — concentrated 8–11 AM, secondary peak Sunday evenings.',
    age: '3 days old',
    tags: ['temporal', 'air-corroborated', '11 supporting entries'],
    confidence: 0.84,
    color: 'rose',
  },
  {
    id: 'sleep-mood',
    kicker: 'next-day effect',
    headlineFrag1: 'Below 6.5h sleep',
    headlineFrag2: 'drops your mood',
    headlineFrag3: '1.2 pts tomorrow.',
    summary: 'Strong inverse correlation (r=−0.71) between deep-sleep minutes and the following day\'s self-reported mood — holds across 28 nights.',
    age: '12 days old',
    tags: ['causal · likely', '28 nights'],
    confidence: 0.78,
    color: 'indigo',
  },
  {
    id: 'shoulders',
    kicker: 'language pattern',
    headlineFrag1: 'You describe',
    headlineFrag2: 'relief in your',
    headlineFrag3: 'shoulders.',
    summary: 'And dread in your jaw. A body-vocabulary that\'s consistent across 17 entries — Iris can listen for the words as early signals.',
    age: '8 days old',
    tags: ['linguistic', 'embodied'],
    confidence: 0.66,
    color: 'amber',
  },
];

// =================== Insights index ===================

function InsightCard({ insight, onOpen }) {
  const colors = { sage: 'var(--sage)', rose: 'var(--rose)', indigo: 'var(--indigo)', amber: 'var(--amber)' };
  const c = colors[insight.color];
  return (
    <article onClick={() => onOpen(insight.id)} style={{
      cursor: 'pointer', padding: '24px 28px',
      background: insight.featured ? 'rgba(169,200,163,0.04)' : 'var(--bg-2)',
      border: '1px solid ' + (insight.featured ? 'var(--sage-dim)' : 'var(--line-soft)'),
      borderRadius: 12, display: 'flex', flexDirection: 'column', gap: 12, minHeight: 280,
      gridColumn: insight.featured ? 'span 2' : 'span 1',
    }}>
      <div className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div className="row" style={{ gap: 8, alignItems: 'baseline' }}>
          <span className="kicker" style={{ color: c }}>{insight.kicker}</span>
          {insight.featured && <span className="tag" style={{ color: 'var(--sage)', borderColor: 'var(--sage-dim)' }}>★ featured · new</span>}
        </div>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{insight.age}</span>
      </div>
      <h3 className="serif" style={{ margin: 0, fontSize: insight.featured ? 48 : 30, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
        {insight.headlineFrag1}<br />
        <span style={{ color: c }}>{insight.headlineFrag2}</span><br />
        <span style={{ fontStyle: 'italic', color: 'var(--ink-2)' }}>{insight.headlineFrag3}</span>
      </h3>
      <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: 'var(--ink-3)', maxWidth: 520 }}>{insight.summary}</p>
      <div style={{ flex: 1 }} />
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
          {insight.tags.map((t, i) => <span key={i} className="tag">{t}</span>)}
        </div>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: c }}>open ↗</span>
      </div>
    </article>
  );
}

function InsightIndex({ onOpen }) {
  return (
    <div className="col" style={{ padding: '32px 56px 48px', gap: 28 }}>
      <header className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid var(--line)', paddingBottom: 18 }}>
        <div className="col" style={{ gap: 6 }}>
          <div className="kicker">insights · what iris has noticed</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 64, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
            12 patterns,<br /><span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>1 new today.</span>
          </h1>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn">all · 12</button>
          <button className="btn">resolved · 3</button>
          <button className="btn">snoozed · 1</button>
        </div>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
        {ALL_INSIGHTS.map(i => <InsightCard key={i.id} insight={i} onOpen={onOpen} />)}
      </div>

      <div className="row" style={{ gap: 14, padding: '16px 18px', border: '1px dashed var(--line)', borderRadius: 10, alignItems: 'center' }}>
        <div className="iris-orb sm" />
        <div style={{ flex: 1 }}>
          <div className="kicker" style={{ color: 'var(--ink-3)' }}>brewing</div>
          <div className="serif ital" style={{ fontSize: 17, color: 'var(--ink-2)' }}>
            Two more patterns need another week of data — I'll surface them when I'm confident.
          </div>
        </div>
      </div>
    </div>
  );
}

// =================== Body-vs-Words deep dive ===================

function BodyVsWordsDetail({ onBack }) {
  // 14 days of (words, body)
  const data = [
    { d: 'Tue 14', words: 5, body: 65 },
    { d: 'Wed 15', words: 4, body: 58 },
    { d: 'Thu 16', words: 6, body: 70 },
    { d: 'Fri 17', words: 7, body: 78 },
    { d: 'Sat 18', words: 8, body: 82 },
    { d: 'Sun 19', words: 7, body: 80 },
    { d: 'Mon 20', words: 3, body: 55 },
    { d: 'Tue 21', words: 4, body: 62 },
    { d: 'Wed 22', words: 6, body: 71 },
    { d: 'Thu 23', words: 5, body: 73 },
    { d: 'Fri 24', words: 7, body: 80 },
    { d: 'Sat 25', words: 8, body: 84 },
    { d: 'Sun 26', words: 7, body: 78 },
    { d: 'Tue 27', words: 4, body: 72 },
  ];

  return (
    <div style={{ padding: '0 0 48px' }}>
      <div className="row" style={{ alignItems: 'center', justifyContent: 'space-between', padding: '20px 40px', borderBottom: '1px solid var(--line-soft)' }}>
        <button className="btn ghost" onClick={onBack} style={{ color: 'var(--ink-3)' }}>← all insights · 12</button>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn">▷ ask iris about this</button>
          <button className="btn">snooze 30d</button>
          <button className="btn">mark resolved</button>
        </div>
      </div>

      <article style={{ padding: '36px 60px 24px', borderBottom: '1px solid var(--line)' }}>
        <div className="row" style={{ gap: 10, marginBottom: 14 }}>
          <span className="tag" style={{ color: 'var(--sage)', borderColor: 'var(--sage-dim)' }}>★ featured</span>
          <span className="tag">fusion · air + journal</span>
          <span className="tag">since may 16</span>
          <span className="tag">11 of last 11 days</span>
          <span className="tag" style={{ color: 'var(--sage)', borderColor: 'var(--sage-dim)' }}>● air-corroborated</span>
        </div>
        <h1 className="serif" style={{ margin: 0, fontSize: 96, lineHeight: 0.92, letterSpacing: '-0.03em' }}>
          Your body forgives you<br />
          <span style={{ color: 'var(--sage)' }}>faster</span> than<br />
          <span style={{ fontStyle: 'italic', color: 'var(--ink-2)' }}>you forgive yourself.</span>
        </h1>
        <p style={{ marginTop: 24, fontSize: 18, lineHeight: 1.55, color: 'var(--ink-2)', maxWidth: 820, fontFamily: 'var(--serif)' }}>
          Over the last two weeks, your overnight HRV recovered to baseline within hours of every stressor — but your self-reported energy and mood took a full day to catch up. The gap averages <span style={{ color: 'var(--sage)' }}>+28 points</span>. You feel worse than you are.
        </p>
      </article>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 36, padding: '32px 60px' }}>
        <div className="col" style={{ gap: 32 }}>
          {/* Twin chart */}
          <section>
            <div className="kicker">14 days · words vs. body</div>
            <h3 className="serif" style={{ margin: '6px 0 16px', fontSize: 24 }}>Two stories of one Sam.</h3>
            <svg width="100%" height="240" viewBox="0 0 700 240">
              {/* gridlines */}
              {[0, 0.25, 0.5, 0.75, 1].map((p, i) => (
                <line key={i} x1="0" y1={20 + p * 180} x2="700" y2={20 + p * 180} stroke="var(--line-soft)" strokeDasharray="2 4" />
              ))}
              {/* Gap shading */}
              {(() => {
                const path = data.map((d, i) => {
                  const x = (i / (data.length - 1)) * 700;
                  const yBody  = 20 + (1 - d.body / 100) * 180;
                  return `${i === 0 ? 'M' : 'L'} ${x} ${yBody}`;
                }).join(' ') + ' ' + data.slice().reverse().map((d, i) => {
                  const idx = data.length - 1 - i;
                  const x = (idx / (data.length - 1)) * 700;
                  const yWords = 20 + (1 - (d.words * 10) / 100) * 180;
                  return `L ${x} ${yWords}`;
                }).join(' ') + ' Z';
                return <path d={path} fill="var(--sage)" opacity="0.08" />;
              })()}
              {/* Body line (top) */}
              {(() => {
                const path = data.map((d, i) => {
                  const x = (i / (data.length - 1)) * 700;
                  const y = 20 + (1 - d.body / 100) * 180;
                  return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
                }).join(' ');
                return (
                  <>
                    <path d={path} stroke="var(--sage)" strokeWidth="1.8" fill="none" />
                    {data.map((d, i) => {
                      const x = (i / (data.length - 1)) * 700;
                      const y = 20 + (1 - d.body / 100) * 180;
                      return <circle key={i} cx={x} cy={y} r="2.5" fill="var(--sage)" />;
                    })}
                  </>
                );
              })()}
              {/* Words line (bottom) */}
              {(() => {
                const path = data.map((d, i) => {
                  const x = (i / (data.length - 1)) * 700;
                  const y = 20 + (1 - (d.words * 10) / 100) * 180;
                  return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
                }).join(' ');
                return (
                  <>
                    <path d={path} stroke="var(--amber)" strokeWidth="1.6" fill="none" strokeDasharray="4 3" />
                    {data.map((d, i) => {
                      const x = (i / (data.length - 1)) * 700;
                      const y = 20 + (1 - (d.words * 10) / 100) * 180;
                      return <circle key={i} cx={x} cy={y} r="2.5" fill="var(--amber)" />;
                    })}
                  </>
                );
              })()}
              {/* Labels */}
              <text x="6" y="14" fontFamily="var(--mono)" fontSize="9" fill="var(--sage)" letterSpacing="0.08em">— BODY · AIR</text>
              <text x="120" y="14" fontFamily="var(--mono)" fontSize="9" fill="var(--amber)" letterSpacing="0.08em">--- WORDS · YOU</text>
              {/* X axis */}
              {data.map((d, i) => i % 2 === 0 && (
                <text key={i} x={(i / (data.length - 1)) * 700} y="232" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)" letterSpacing="0.04em">{d.d}</text>
              ))}
              {/* Annotation: Monday */}
              <line x1={(6 / 13) * 700} y1="20" x2={(6 / 13) * 700} y2="200" stroke="var(--rose)" strokeDasharray="2 3" opacity="0.6" />
              <text x={(6 / 13) * 700 + 4} y="30" fontFamily="var(--mono)" fontSize="9" fill="var(--rose)" letterSpacing="0.04em">mon · biggest gap</text>
            </svg>
          </section>

          {/* The shape of the gap */}
          <section>
            <div className="kicker">how it shows up</div>
            <h3 className="serif" style={{ margin: '6px 0 16px', fontSize: 24 }}>The shape of the gap.</h3>
            <div className="row" style={{ gap: 24, padding: '20px 0', alignItems: 'flex-end', borderTop: '1px solid var(--line-soft)' }}>
              <div className="col" style={{ alignItems: 'flex-start', gap: 4 }}>
                <div className="numerals" style={{ fontSize: 80, color: 'var(--sage)' }}>+28</div>
                <div className="kicker">avg gap · last 14d</div>
              </div>
              <div className="col" style={{ alignItems: 'flex-start', gap: 4 }}>
                <div className="numerals" style={{ fontSize: 80, color: 'var(--ink)' }}>22 <span style={{ fontSize: 18, color: 'var(--ink-3)', letterSpacing: '0.06em' }}>HOURS</span></div>
                <div className="kicker">how long words lag</div>
              </div>
              <div className="col" style={{ alignItems: 'flex-start', gap: 4 }}>
                <div className="numerals" style={{ fontSize: 80, color: 'var(--rose)' }}>+42</div>
                <div className="kicker">peak gap · monday</div>
              </div>
            </div>
          </section>

          {/* Pull quote pairing */}
          <section>
            <div className="kicker">what you wrote · what the air saw</div>
            <h3 className="serif" style={{ margin: '6px 0 16px', fontSize: 24 }}>Three nights this week.</h3>
            <div className="col" style={{ gap: 18 }}>
              {[
                { date: 'Mon, May 20', wrote: "Couldn't get my breath until 10. The day felt like it started without me.", air: 'HRV +6 ms within 4 hrs · breathing rate quieted by noon', verdict: 'recovered by lunch · you didn\'t know' },
                { date: 'Thu, May 23', wrote: "Couldn't sleep. Mind on the design review.", air: 'Deep sleep 1h 02m · low for you · but HRV held at 49', verdict: 'body kept its baseline · the mind didn\'t' },
                { date: 'Tue, May 27', wrote: "Honestly kind of fried.", air: 'HRV +9 ms vs yesterday · breath quieted by 3 PM', verdict: 'you\'re less fried than you feel' },
              ].map((p, i) => (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: '110px 1fr 1fr', gap: 18, padding: '16px 0', borderTop: '1px solid var(--line-soft)' }}>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)', letterSpacing: '0.08em', textTransform: 'uppercase', paddingTop: 4 }}>{p.date}</span>
                  <div className="col" style={{ gap: 4 }}>
                    <span className="kicker" style={{ color: 'var(--amber)' }}>words</span>
                    <span className="serif ital" style={{ fontSize: 17, color: 'var(--ink)', lineHeight: 1.4 }}>"{p.wrote}"</span>
                  </div>
                  <div className="col" style={{ gap: 4 }}>
                    <span className="kicker" style={{ color: 'var(--sage)' }}>body · air</span>
                    <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink-2)' }}>{p.air}</span>
                    <span style={{ fontSize: 11, color: 'var(--sage)', fontStyle: 'italic', marginTop: 2 }}>{p.verdict}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <aside className="col" style={{ gap: 28 }}>
          <section style={{ padding: '20px 22px', background: 'var(--bg-2)', border: '1px solid var(--line-soft)', borderRadius: 10 }}>
            <div className="row" style={{ gap: 10, alignItems: 'center', marginBottom: 10 }}>
              <div className="iris-orb sm" />
              <span className="kicker">iris's read</span>
            </div>
            <div className="serif ital" style={{ fontSize: 18, lineHeight: 1.4, color: 'var(--ink)' }}>
              "This isn't denial — your body really has bounced back. It's that the story you tell about a hard day lasts longer than the hard day. That gap is workable."
            </div>
          </section>

          <section>
            <div className="kicker" style={{ marginBottom: 8 }}>things to try</div>
            <div className="col" style={{ gap: 10 }}>
              {[
                { label: 'At 9 PM, Iris shows you today\'s HRV before you write', impact: 'meet the day with both stories' },
                { label: 'Mid-day glance: "you\'re at 68, words say 42"', impact: 'gentle calibration in the moment' },
                { label: 'Sunday review reframes a hard week against body data', impact: 'shorten the story\'s shadow' },
                { label: 'Anchor phrase: "the body has already turned"', impact: 'a sentence to hold on Monday morning' },
              ].map((s, i) => (
                <button key={i} className="col" style={{
                  alignItems: 'flex-start', gap: 4, background: 'transparent',
                  border: '1px solid var(--line)', borderRadius: 8, padding: '10px 14px',
                  textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit', color: 'inherit',
                }}>
                  <span style={{ fontSize: 13, color: 'var(--ink)' }}>{s.label}</span>
                  <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>{s.impact}</span>
                </button>
              ))}
            </div>
          </section>

          <section>
            <div className="kicker" style={{ marginBottom: 10 }}>related</div>
            <div className="col" style={{ gap: 8 }}>
              {[
                ['Monday anxiety (32% higher)', 'temporal'],
                ['Sleep ↔ next-day mood (r=−0.71)', 'causal'],
                ['Shoulder = relief, jaw = dread', 'language'],
              ].map(([t, tag], i) => (
                <div key={i} className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 13, color: 'var(--ink-2)' }}>{t}</span>
                  <span className="tag">{tag}</span>
                </div>
              ))}
            </div>
          </section>

          <section style={{ paddingTop: 14, borderTop: '1px dashed var(--line)' }}>
            <div className="kicker" style={{ marginBottom: 6 }}>how iris found this</div>
            <div style={{ fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.55, fontStyle: 'italic' }}>
              Twin time-series: overnight HRV recovery from Fitbit Air vs. next-morning self-rated energy & mood. Required 14+ days of both signals.
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

// =================== Monday-anxiety detail (existing, lightly extracted) ===================

const MONDAY_HOURS = Array.from({ length: 168 }, (_, i) => {
  const day = Math.floor(i / 24);
  const hour = i % 24;
  if (day === 0 && hour >= 8 && hour <= 11) return 0.85 + ((i*7)%5)*0.02;
  if (day === 0 && hour >= 6 && hour <= 14) return 0.55 + ((i*3)%5)*0.03;
  if (day === 6 && hour >= 18) return 0.45;
  if (hour >= 8 && hour <= 11) return 0.35 + ((i*11)%5)*0.04;
  return 0.1 + ((i*17)%5)*0.04;
});

const PULL_QUOTES = [
  { date: 'Mon, May 19', text: "Couldn't get my breath until 10. The day felt like it started without me." },
  { date: 'Mon, May 12', text: "I keep waking up already behind." },
  { date: 'Mon, May 5',  text: "Why does Monday feel like Sunday night, but worse." },
  { date: 'Mon, Apr 28', text: "Stomach in knots through standup again. Joel asked if I was okay." },
];

function MondayDetail({ onBack }) {
  return (
    <div style={{ padding: '0 0 48px' }}>
      <div className="row" style={{ alignItems: 'center', justifyContent: 'space-between', padding: '20px 40px', borderBottom: '1px solid var(--line-soft)' }}>
        <button className="btn ghost" onClick={onBack} style={{ color: 'var(--ink-3)' }}>← all insights · 12</button>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn">▷ ask iris about this</button>
          <button className="btn">snooze 30d</button>
          <button className="btn">mark resolved</button>
        </div>
      </div>

      <article style={{ padding: '36px 60px 24px', borderBottom: '1px solid var(--line)', maxWidth: 1180 }}>
        <div className="row" style={{ gap: 10, marginBottom: 14 }}>
          <span className="tag" style={{ color: 'var(--rose)', borderColor: 'var(--rose)' }}>pattern</span>
          <span className="tag">temporal</span>
          <span className="tag">since apr 14</span>
          <span className="tag">11 supporting entries</span>
          <span className="tag" style={{ color: 'var(--sage)', borderColor: 'var(--sage-dim)' }}>● air-corroborated</span>
        </div>
        <h1 className="serif" style={{ margin: 0, fontSize: 88, lineHeight: 0.92, letterSpacing: '-0.03em' }}>
          You are <span style={{ color: 'var(--rose)' }}>32%</span><br />
          more anxious<br />
          <span style={{ fontStyle: 'italic', color: 'var(--ink-2)' }}>on Mondays.</span>
        </h1>
        <p style={{ marginTop: 22, fontSize: 17, lineHeight: 1.55, color: 'var(--ink-2)', maxWidth: 760, fontFamily: 'var(--serif)' }}>
          Across the last 11 weeks, your morning anxiety rises an average of 32% on Mondays vs. the rest of the week — almost entirely concentrated between 8 and 11 AM, with a smaller secondary peak on Sunday evenings.
        </p>
      </article>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 36, padding: '32px 60px' }}>
        <div className="col" style={{ gap: 32 }}>
          <section>
            <div className="kicker">the shape of your week</div>
            <h3 className="serif" style={{ margin: '6px 0 16px', fontSize: 24 }}>Anxiety, hour by hour.</h3>
            <svg width="700" height="180" viewBox="0 0 700 180" style={{ width: '100%', height: 'auto' }}>
              <line x1="0" y1="160" x2="700" y2="160" stroke="var(--line)" />
              {[1,2,3,4,5,6].map(i => (
                <line key={i} x1={i*100} y1="0" x2={i*100} y2="170" stroke="var(--line-soft)" strokeDasharray="2 4" />
              ))}
              <path d={(() => {
                let d = `M 0 ${160 - MONDAY_HOURS[0] * 140}`;
                for (let i = 1; i < MONDAY_HOURS.length; i++) {
                  d += ` L ${(i / 167) * 700} ${160 - MONDAY_HOURS[i] * 140}`;
                }
                return d;
              })()} stroke="var(--rose)" strokeWidth="1.4" fill="none" />
              <rect x="0" y="0" width="100" height="170" fill="var(--rose)" opacity="0.06" />
              <text x="50" y="14" textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="var(--rose)" letterSpacing="0.1em">MON</text>
              {['MON','TUE','WED','THU','FRI','SAT','SUN'].map((d, i) => (
                <text key={d} x={i*100 + 50} y="178" textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)" letterSpacing="0.1em">{d}</text>
              ))}
              <line x1="40" y1="40" x2="40" y2="80" stroke="var(--amber)" strokeWidth="0.8" />
              <text x="46" y="44" fontFamily="var(--mono)" fontSize="10" fill="var(--amber)" letterSpacing="0.04em">9 am peak</text>
            </svg>
          </section>

          <section>
            <div className="kicker">in your own words</div>
            <h3 className="serif" style={{ margin: '6px 0 16px', fontSize: 24 }}>Four mondays.</h3>
            <div className="col" style={{ gap: 14 }}>
              {PULL_QUOTES.map((q, i) => (
                <blockquote key={i} style={{ margin: 0, padding: '0 0 0 18px', borderLeft: '2px solid var(--rose)' }}>
                  <div className="serif" style={{ fontSize: 19, fontStyle: 'italic', lineHeight: 1.4, color: 'var(--ink)' }}>"{q.text}"</div>
                  <div style={{ marginTop: 6, fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{q.date} · journal entry</div>
                </blockquote>
              ))}
            </div>
          </section>
        </div>

        <aside className="col" style={{ gap: 28 }}>
          <section style={{ padding: '20px 22px', background: 'var(--bg-2)', border: '1px solid var(--line-soft)', borderRadius: 10 }}>
            <div className="row" style={{ gap: 10, alignItems: 'center', marginBottom: 10 }}>
              <div className="iris-orb sm" />
              <span className="kicker">iris's read</span>
            </div>
            <div className="serif ital" style={{ fontSize: 18, lineHeight: 1.4, color: 'var(--ink)' }}>
              "I think two things stack on Mondays — Sunday-night dread leaking into your sleep, and the standup itself. The pattern eases by noon, which is hopeful."
            </div>
          </section>

          <section>
            <div className="kicker" style={{ marginBottom: 8 }}>things to try</div>
            <div className="col" style={{ gap: 10 }}>
              {[
                { label: 'Pre-write Monday\'s standup on Sunday at 5pm', impact: 'shifts dread → drafting' },
                { label: 'Walk before 9 AM on Mondays', impact: 'cuts cortisol spike' },
                { label: 'Schedule something gentle Monday lunch', impact: 'creates a 12pm landmark' },
              ].map((s, i) => (
                <button key={i} className="col" style={{
                  alignItems: 'flex-start', gap: 4, background: 'transparent',
                  border: '1px solid var(--line)', borderRadius: 8, padding: '10px 14px',
                  textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit', color: 'inherit',
                }}>
                  <span style={{ fontSize: 13, color: 'var(--ink)' }}>{s.label}</span>
                  <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>{s.impact}</span>
                </button>
              ))}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

// =================== Router ===================

function InsightScreen() {
  const [view, setView] = React.useState('index'); // 'index' | 'body-words' | 'monday'

  if (view === 'body-words') return <BodyVsWordsDetail onBack={() => setView('index')} />;
  if (view === 'monday')     return <MondayDetail onBack={() => setView('index')} />;
  return <InsightIndex onOpen={(id) => {
    if (id === 'body-words' || id === 'monday') setView(id);
    else setView('body-words'); // other cards open body-words for demo
  }} />;
}

window.InsightScreen = InsightScreen;

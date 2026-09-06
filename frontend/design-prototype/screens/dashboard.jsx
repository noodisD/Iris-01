// screens/dashboard.jsx — "Today" analytics page (dense, editorial)

// ─── Generated data (stable per session) ───
const mkSeries = (n, base, amp, seed) => {
  let s = seed;
  return Array.from({ length: n }, (_, i) => {
    s = (s * 9301 + 49297) % 233280;
    const r = s / 233280;
    return Math.round((base + Math.sin(i / 1.8) * amp * 0.6 + (r - 0.5) * amp) * 10) / 10;
  });
};

const today = {
  moodWeek: mkSeries(14, 6.2, 1.8, 7),
  energyWeek: mkSeries(14, 5.5, 2.2, 11),
  sleepBars: [6.8, 7.1, 5.4, 6.2, 7.9, 8.1, 7.4, 6.5, 5.9, 7.2, 7.8, 6.4, 7.5, 6.9],
  anxietyHeat: Array.from({ length: 7 }, (_, r) =>
    Array.from({ length: 24 }, (_, c) => {
      const morning = c >= 6 && c <= 10 && r < 5 ? 0.7 : 0;
      const evening = c >= 21 && c <= 23 ? 0.4 : 0;
      const random = ((r * 13 + c * 7) % 11) / 22;
      return Math.min(1, morning + evening * 0.6 + random);
    })),
  focusRing: 0.68,
  socialRing: 0.42,
  habitsDots: Array.from({ length: 7 * 6 }, (_, i) => ((i * 7 + 3) % 9) / 9),
  topics: [
    { name: 'work',          count: 38, trend: 'up',   color: 'var(--ink-2)' },
    { name: 'relationships', count: 22, trend: 'flat', color: 'var(--sage)' },
    { name: 'health',        count: 19, trend: 'up',   color: 'var(--amber)' },
    { name: 'creativity',    count: 14, trend: 'down', color: 'var(--indigo)' },
    { name: 'finance',       count: 11, trend: 'flat', color: 'var(--ink-3)' },
    { name: 'family',        count: 9,  trend: 'up',   color: 'var(--rose)' },
  ],
};

function DashCard({ kicker, title, big, suffix, sub, footer, children, span = 1, accent = 'var(--ink)', flush = false }) {
  return (
    <div style={{
      gridColumn: `span ${span}`,
      background: flush ? 'transparent' : 'var(--bg-2)',
      border: flush ? 'none' : '1px solid var(--line-soft)',
      borderRadius: 10,
      padding: '18px 20px 16px',
      display: 'flex', flexDirection: 'column', gap: 12,
      minHeight: 160,
    }}>
      <div className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div className="kicker">{kicker}</div>
        {title && <div style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--mono)' }}>{title}</div>}
      </div>
      {big && (
        <div className="numerals" style={{ fontSize: 56, color: accent }}>
          {big}{suffix && <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink-3)', marginLeft: 6, letterSpacing: '0.08em', textTransform: 'uppercase' }}>{suffix}</span>}
        </div>
      )}
      {sub && <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>{sub}</div>}
      <div style={{ flex: 1, display: 'flex', alignItems: 'flex-end' }}>{children}</div>
      {footer && <div className="row" style={{ justifyContent: 'space-between', fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.06em', color: 'var(--ink-4)', textTransform: 'uppercase' }}>{footer}</div>}
    </div>
  );
}

function MoodFace({ score }) {
  // simple editorial mood face — line drawn
  const happy = score / 10; // 0..1
  const mouthY = 36 - (happy - 0.5) * 8;
  const curve = (happy - 0.5) * 14;
  return (
    <svg width="56" height="56" viewBox="0 0 56 56">
      <circle cx="28" cy="28" r="22" stroke="currentColor" strokeWidth="1.2" fill="none" />
      <circle cx="20" cy="24" r="1.6" fill="currentColor" />
      <circle cx="36" cy="24" r="1.6" fill="currentColor" />
      <path d={`M 18 ${mouthY} Q 28 ${mouthY + curve} 38 ${mouthY}`} stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" />
    </svg>
  );
}

function DashboardScreen() {
  return (
    <div className="col" style={{ padding: '24px 32px 40px', gap: 24 }}>
      {/* Top header — newspaper masthead */}
      <header className="row" style={{ alignItems: 'flex-end', justifyContent: 'space-between', borderBottom: '1px solid var(--line)', paddingBottom: 16 }}>
        <div className="col" style={{ gap: 4 }}>
          <div className="kicker">Tuesday, May 27 · 7:42 PM · Day 47</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 56, letterSpacing: '-0.025em', lineHeight: 1 }}>
            Today's reading<span style={{ color: 'var(--sage)' }}>.</span>
          </h1>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn">← yesterday</button>
          <button className="btn">week</button>
          <button className="btn">month</button>
          <button className="btn primary">▷ Daily check-in</button>
        </div>
      </header>

      {/* Iris's headline insight */}
      <div className="row" style={{ gap: 18, alignItems: 'flex-start', padding: '8px 0 12px', borderBottom: '1px dashed var(--line)' }}>
        <div className="iris-orb" style={{ marginTop: 6 }} />
        <div className="col" style={{ flex: 1, gap: 4 }}>
          <div className="kicker">Iris, just now</div>
          <div className="serif" style={{ fontSize: 26, fontStyle: 'italic', letterSpacing: '-0.005em', lineHeight: 1.3, color: 'var(--ink)', maxWidth: 880 }}>
            "You're running on yesterday's sleep and skipped lunch — but the design review is off your back. Tonight feels like a soft landing, not a goal."
          </div>
        </div>
        <button className="btn" style={{ alignSelf: 'flex-start' }}>↗ open</button>
      </div>

      {/* Main grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: 14 }}>
        {/* Mood — big */}
        <DashCard kicker="Mood" title="7-day" big="6.4" suffix="/10" span={3} accent="var(--ink)"
                  footer={[<span key="a">Δ +0.6 vs wk</span>, <span key="b">var.med</span>]}>
          <div className="col" style={{ gap: 10, width: '100%' }}>
            <div style={{ color: 'var(--sage)' }}><MoodFace score={6.4} /></div>
            <Sparkline data={today.moodWeek} w={220} h={36} stroke="var(--sage)" fill dots />
          </div>
        </DashCard>

        {/* Energy */}
        <DashCard kicker="Energy" title="now" big="38" suffix="/100" span={3} accent="var(--amber)"
                  footer={[<span key="a">trending ↓</span>, <span key="b">peak 11am</span>]}>
          <div className="col" style={{ gap: 8, width: '100%' }}>
            <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>You drop 22% after 3 PM on no-lunch days.</div>
            <Sparkline data={today.energyWeek} w={220} h={36} stroke="var(--amber)" fill />
          </div>
        </DashCard>

        {/* Sleep */}
        <DashCard kicker="Sleep" title="last 14 nights" big="6h 52m" span={3} accent="var(--indigo)"
                  footer={[<span key="a">debt 3h 18m</span>, <span key="b">avg 7h 04m</span>]}>
          <BarSeries data={today.sleepBars} w={220} h={48} color={(d) => d < 6.5 ? 'var(--rose)' : d < 7.2 ? 'var(--amber)' : 'var(--indigo)'} />
        </DashCard>

        {/* Focus + Social rings */}
        <DashCard kicker="Today's rings" span={3}>
          <div className="row" style={{ gap: 20, justifyContent: 'center', width: '100%', marginTop: 8 }}>
            <div className="col" style={{ alignItems: 'center', gap: 6 }}>
              <Ring value={today.focusRing} size={80} stroke={6} color="var(--sage)" label="68" />
              <span className="eyebrow">focus</span>
            </div>
            <div className="col" style={{ alignItems: 'center', gap: 6 }}>
              <Ring value={today.socialRing} size={80} stroke={6} color="var(--rose)" label="42" />
              <span className="eyebrow">social</span>
            </div>
          </div>
        </DashCard>

        {/* Anxiety heatmap — full width */}
        <DashCard kicker="Anxiety" title="hour × weekday · last 4 wks" span={7}
                  footer={[<span key="a">peaks · mon 9am · tue 9am · sun 10pm</span>, <span key="b">cooler · sat morning</span>]}>
          <div className="col" style={{ gap: 6, width: '100%' }}>
            <div className="row" style={{ gap: 12, alignItems: 'flex-end' }}>
              <div className="col" style={{ gap: 4, justifyContent: 'space-between', fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink-4)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                {['mon','tue','wed','thu','fri','sat','sun'].map(d => <span key={d}>{d}</span>)}
              </div>
              <HeatGrid matrix={today.anxietyHeat} cellW={18} cellH={11} gap={2} color="212,138,138" />
            </div>
            <div className="row" style={{ justifyContent: 'space-between', fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink-4)', letterSpacing: '0.04em', textTransform: 'uppercase', paddingLeft: 30 }}>
              <span>12a</span><span>6a</span><span>noon</span><span>6p</span><span>11p</span>
            </div>
          </div>
        </DashCard>

        {/* Topics — what we talk about */}
        <DashCard kicker="What we talk about" title="this month" span={5}>
          <div className="col" style={{ gap: 8, width: '100%' }}>
            {today.topics.map(t => (
              <div key={t.name} className="row" style={{ alignItems: 'center', gap: 10 }}>
                <span style={{ width: 80, fontSize: 12, color: 'var(--ink)', fontFamily: 'var(--mono)' }}>{t.name}</span>
                <div style={{ flex: 1, height: 6, background: 'var(--bg-3)', borderRadius: 999, overflow: 'hidden' }}>
                  <div style={{ width: `${t.count * 1.8}%`, height: '100%', background: t.color, borderRadius: 999 }} />
                </div>
                <span style={{ width: 28, textAlign: 'right', fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-3)' }}>{t.count}</span>
                <span style={{ width: 14, color: t.trend === 'up' ? 'var(--sage)' : t.trend === 'down' ? 'var(--rose)' : 'var(--ink-3)', fontFamily: 'var(--mono)', fontSize: 11 }}>
                  {t.trend === 'up' ? '↗' : t.trend === 'down' ? '↘' : '→'}
                </span>
              </div>
            ))}
          </div>
        </DashCard>

        {/* Habits dot calendar */}
        <DashCard kicker="Habits" title="6 weeks" span={4}
                  footer={[<span key="a">longest streak — 14d (meditate)</span>, <span key="b">3 of 5 today</span>]}>
          <div className="col" style={{ gap: 4, width: '100%' }}>
            <div className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
              <DotMatrix values={today.habitsDots} cols={7} rows={6} dot={14} gap={4}
                colorFor={(v) => v > 0.7 ? 'var(--sage)' : v > 0.3 ? 'rgba(169,200,163,0.35)' : 'var(--line)'} />
              <div className="col" style={{ gap: 10, fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)', letterSpacing: '0.04em', flex: 1 }}>
                <div className="row" style={{ gap: 6, alignItems: 'center' }}><span className="dot sage" />meditate · 14d</div>
                <div className="row" style={{ gap: 6, alignItems: 'center' }}><span className="dot" style={{ background: 'rgba(169,200,163,0.5)' }} />walk · 9d</div>
                <div className="row" style={{ gap: 6, alignItems: 'center' }}><span className="dot" style={{ background: 'rgba(169,200,163,0.3)' }} />read · 4d</div>
                <div className="row" style={{ gap: 6, alignItems: 'center' }}><span className="dot" style={{ background: 'var(--line)' }} />no-phone-bed · 0d</div>
              </div>
            </div>
          </div>
        </DashCard>

        {/* Correlations card */}
        <DashCard kicker="Iris correlated" title="last 30d" span={4}>
          <div className="col" style={{ gap: 8, width: '100%' }}>
            <div className="row" style={{ gap: 10, alignItems: 'baseline' }}>
              <span className="numerals" style={{ fontSize: 26, color: 'var(--sage)' }}>0.72</span>
              <span style={{ fontSize: 12, color: 'var(--ink-2)' }}>sleep ↔ mood next day</span>
            </div>
            <div className="row" style={{ gap: 10, alignItems: 'baseline' }}>
              <span className="numerals" style={{ fontSize: 26, color: 'var(--amber)' }}>0.51</span>
              <span style={{ fontSize: 12, color: 'var(--ink-2)' }}>morning walk ↔ focus</span>
            </div>
            <div className="row" style={{ gap: 10, alignItems: 'baseline' }}>
              <span className="numerals" style={{ fontSize: 26, color: 'var(--rose)' }}>−0.44</span>
              <span style={{ fontSize: 12, color: 'var(--ink-2)' }}>screen 9–11pm ↔ deep sleep</span>
            </div>
          </div>
        </DashCard>

        {/* Today's wins */}
        <DashCard kicker="Wins, today" span={4}>
          <div className="col" style={{ gap: 10, width: '100%' }}>
            <div className="serif" style={{ fontSize: 18, fontStyle: 'italic', lineHeight: 1.3, color: 'var(--ink)' }}>
              "Shipped the design review."
            </div>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
              <span className="tag">+1 work</span>
              <span className="tag">+1 streak: ship</span>
              <span className="tag">9 days carried</span>
            </div>
            <hr className="dotline" />
            <div style={{ fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.5 }}>
              You've logged <span style={{ color: 'var(--ink)' }}>11 wins</span> this month — most under "work" and "creativity." Want Iris to ask you each evening?
            </div>
          </div>
        </DashCard>

        {/* Worry — tied for clarity */}
        <DashCard kicker="Worries — currently held" span={4}>
          <div className="col" style={{ gap: 8, width: '100%' }}>
            {[
              ['budget conversation w/ Joel', '5 days', 'high'],
              ['mom\'s appointment', '11 days', 'med'],
              ['where to go in August?', '3 weeks', 'low'],
            ].map(([w, days, p], i) => (
              <div key={i} className="col" style={{ gap: 2 }}>
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 13, color: 'var(--ink)' }}>{w}</span>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: p==='high'?'var(--rose)':p==='med'?'var(--amber)':'var(--ink-3)' }}>{p}</span>
                </div>
                <span style={{ fontSize: 11, color: 'var(--ink-4)' }}>carried for {days}</span>
              </div>
            ))}
          </div>
        </DashCard>

        {/* HRV — from Fitbit Air */}
        <DashCard kicker="HRV · last night · air" span={4} accent="var(--sage)"
                  footer={[<span key="a">↑ 9 ms vs yesterday</span>, <span key="b">↗ open body screen</span>]}>
          <div className="col" style={{ gap: 6, width: '100%' }}>
            <div className="row" style={{ gap: 12, alignItems: 'baseline' }}>
              <div className="numerals" style={{ fontSize: 56, color: 'var(--sage)' }}>54<span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink-3)', letterSpacing: '0.06em', marginLeft: 6 }}>MS</span></div>
              <div className="col" style={{ gap: 2 }}>
                <span style={{ fontSize: 11, color: 'var(--sage)', fontFamily: 'var(--mono)' }}>↑ 12% baseline</span>
                <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>system, calmer</span>
              </div>
            </div>
            <Sparkline data={today.moodWeek.map((m, i) => 40 + m * 2 + i * 0.4)} w={240} h={32} stroke="var(--sage)" fill />
          </div>
        </DashCard>

        {/* Readiness — Fitbit Air */}
        <DashCard kicker="Readiness · today · air" span={4} accent="var(--sage)"
                  footer={[<span key="a">14-day avg 67</span>, <span key="b">body says · go gently</span>]}>
          <div className="row" style={{ gap: 16, alignItems: 'center', width: '100%' }}>
            <Ring value={0.72} size={88} stroke={7} color="var(--sage)" label={<span style={{ fontFamily: 'var(--serif)', fontSize: 22, color: 'var(--ink)' }}>72</span>} />
            <div className="col" style={{ gap: 4 }}>
              <div className="row" style={{ alignItems: 'baseline', gap: 8 }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.06em' }}>WORDS</span>
                <span className="serif" style={{ fontSize: 18, color: 'var(--amber)' }}>38</span>
              </div>
              <div className="row" style={{ alignItems: 'baseline', gap: 8 }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.06em' }}>GAP</span>
                <span className="serif" style={{ fontSize: 18, color: 'var(--ink)' }}>+34</span>
              </div>
              <span style={{ fontSize: 10, color: 'var(--ink-3)', fontStyle: 'italic', maxWidth: 130, lineHeight: 1.35 }}>your body has more in the tank than your words admit</span>
            </div>
          </div>
        </DashCard>
      </div>

      {/* Footnote */}
      <div className="row" style={{ justifyContent: 'space-between', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.06em', textTransform: 'uppercase', paddingTop: 8 }}>
        <span>Issue 047 · vol. 1 · printed for sam</span>
        <span>last sync — 4 min ago · 2 patterns updated</span>
      </div>
    </div>
  );
}

window.DashboardScreen = DashboardScreen;

// screens/review.jsx — Cinematic weekly review (single hero letter)

const WEEK_DAYS = [
  { day: 'mon', date: 20, mood: 4.8, sleep: 5.9, word: 'tight'   },
  { day: 'tue', date: 21, mood: 5.6, sleep: 6.4, word: 'fried'   },
  { day: 'wed', date: 22, mood: 6.7, sleep: 7.4, word: 'steady'  },
  { day: 'thu', date: 23, mood: 5.2, sleep: 6.1, word: 'tired'   },
  { day: 'fri', date: 24, mood: 7.4, sleep: 7.2, word: 'open'    },
  { day: 'sat', date: 25, mood: 8.1, sleep: 8.1, word: 'slow'    },
  { day: 'sun', date: 26, mood: 7.3, sleep: 7.4, word: 'quiet'   },
];

function ReviewScreen() {
  const moodAvg = (WEEK_DAYS.reduce((s, d) => s + d.mood, 0) / WEEK_DAYS.length).toFixed(1);
  const sleepAvg = (WEEK_DAYS.reduce((s, d) => s + d.sleep, 0) / WEEK_DAYS.length).toFixed(1);

  return (
    <div className="col" style={{ minHeight: '100%', padding: 0 }}>
      {/* Top strip */}
      <div className="row" style={{ alignItems: 'center', justifyContent: 'space-between', padding: '20px 56px', borderBottom: '1px solid var(--line-soft)' }}>
        <div className="row" style={{ gap: 10, alignItems: 'baseline' }}>
          <span className="kicker">your week · may 20 — 26 · iss. 18</span>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn">← prev week</button>
          <button className="btn">this week →</button>
          <button className="btn primary">▷ Read aloud · 2 min</button>
        </div>
      </div>

      {/* Hero — Iris's letter, full-bleed */}
      <section style={{
        flex: 1,
        padding: '90px 0 56px',
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        position: 'relative',
        background: 'radial-gradient(ellipse at top, rgba(169,200,163,0.04) 0%, transparent 70%)',
      }}>
        {/* tiny breathing orb at top */}
        <div className="iris-orb" style={{ marginBottom: 28 }} />

        <div style={{ maxWidth: 760, padding: '0 56px', textAlign: 'left' }}>
          <div className="kicker" style={{ marginBottom: 18, textAlign: 'center' }}>iris's letter · sun morning · 6:03 am</div>
          <h1 className="serif" style={{
            margin: 0, fontSize: 64, lineHeight: 1.05, letterSpacing: '-0.022em', color: 'var(--ink)',
            textWrap: 'pretty',
          }}>
            Sam,
          </h1>
          <div className="serif" style={{
            fontSize: 28, lineHeight: 1.5, letterSpacing: '-0.005em', color: 'var(--ink)',
            marginTop: 22, textWrap: 'pretty',
          }}>
            Your week started <em style={{ color: 'var(--rose)' }}>tight</em>. By Friday's walk, your shoulders dropped a vocabulary level — you said <em style={{ color: 'var(--sage)' }}>"open"</em> for the first time in nineteen days.
          </div>
          <div className="serif" style={{
            fontSize: 24, lineHeight: 1.55, letterSpacing: '-0.003em', color: 'var(--ink-2)',
            marginTop: 26, fontStyle: 'italic', textWrap: 'pretty',
          }}>
            The thing you carried longest — the design review — is off your back. Notice what's landing in the space where it lived.
          </div>
          <div style={{
            marginTop: 28, fontFamily: 'var(--serif)', fontSize: 22, color: 'var(--ink-3)', fontStyle: 'italic',
          }}>
            — Iris
          </div>
        </div>

        {/* Subtle inline numbers — read as a footer to the letter */}
        <div className="row" style={{ gap: 48, marginTop: 64, padding: '32px 56px 0', borderTop: '1px dashed var(--line)', maxWidth: 760, width: '100%' }}>
          <div className="col" style={{ gap: 2 }}>
            <span className="numerals" style={{ fontSize: 40, color: 'var(--sage)' }}>{moodAvg}</span>
            <span className="kicker">mood · +0.6</span>
          </div>
          <div className="col" style={{ gap: 2 }}>
            <span className="numerals" style={{ fontSize: 40, color: 'var(--indigo)' }}>{sleepAvg}<span style={{ fontSize: 14, color: 'var(--ink-3)' }}>h</span></span>
            <span className="kicker">sleep · +12m</span>
          </div>
          <div className="col" style={{ gap: 2 }}>
            <span className="numerals" style={{ fontSize: 40, color: 'var(--ink)' }}>23<span style={{ fontSize: 14, color: 'var(--ink-3)' }}>/35</span></span>
            <span className="kicker">habits hit</span>
          </div>
          <div className="col" style={{ gap: 2 }}>
            <span className="numerals" style={{ fontSize: 40, color: 'var(--amber)' }}>4</span>
            <span className="kicker">wins logged</span>
          </div>
          <div className="col" style={{ gap: 2 }}>
            <span className="numerals" style={{ fontSize: 40, color: 'var(--sage)' }}>+5<span style={{ fontSize: 14, color: 'var(--ink-3)' }}>ms</span></span>
            <span className="kicker">hrv · air</span>
          </div>
        </div>
      </section>

      {/* The week as a 7-glyph poem */}
      <section style={{ padding: '40px 56px 30px', borderTop: '1px solid var(--line-soft)' }}>
        <div className="kicker" style={{ marginBottom: 24, textAlign: 'center' }}>· seven words for seven days ·</div>
        <div className="row" style={{ justifyContent: 'space-between', gap: 14, maxWidth: 1080, margin: '0 auto', alignItems: 'flex-end' }}>
          {WEEK_DAYS.map((d, i) => {
            const intensity = d.mood / 10;
            return (
              <div key={i} className="col" style={{ alignItems: 'center', gap: 10, flex: 1 }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>{d.day} {d.date}</span>
                <div style={{
                  width: 8 + intensity * 32, height: 8 + intensity * 32, borderRadius: '50%',
                  background: `radial-gradient(circle at 35% 30%, var(--orb-hue-a), var(--orb-hue-b) 55%, var(--orb-hue-c) 100%)`,
                  opacity: 0.5 + intensity * 0.5,
                }} />
                <span className="serif" style={{ fontSize: 22, fontStyle: 'italic', color: 'var(--ink)' }}>{d.word}</span>
              </div>
            );
          })}
        </div>
      </section>

      {/* Three small columns — themes, win, ahead */}
      <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 0, padding: '32px 56px 48px', borderTop: '1px solid var(--line-soft)' }}>
        <div className="col" style={{ gap: 8, padding: '0 32px 0 0' }}>
          <div className="kicker">three themes</div>
          <ol style={{ margin: 0, paddingLeft: 22, color: 'var(--ink)' }}>
            <li className="serif" style={{ fontSize: 18, fontStyle: 'italic', lineHeight: 1.4, marginBottom: 6 }}>The body keeps the schedule.</li>
            <li className="serif" style={{ fontSize: 18, fontStyle: 'italic', lineHeight: 1.4, marginBottom: 6, color: 'var(--ink-2)' }}>Slow mornings undo something.</li>
            <li className="serif" style={{ fontSize: 18, fontStyle: 'italic', lineHeight: 1.4, color: 'var(--ink-2)' }}>"Open" is back in your vocabulary.</li>
          </ol>
        </div>
        <div className="col" style={{ gap: 8, padding: '0 32px', borderLeft: '1px dashed var(--line)' }}>
          <div className="kicker">the win that mattered</div>
          <div className="serif" style={{ fontSize: 22, fontStyle: 'italic', lineHeight: 1.3, color: 'var(--ink)' }}>"Shipped the design review."</div>
          <div style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>carried 9 days · resolved tuesday 4pm</div>
        </div>
        <div className="col" style={{ gap: 8, padding: '0 0 0 32px', borderLeft: '1px dashed var(--line)' }}>
          <div className="kicker">looking ahead</div>
          <div className="col" style={{ gap: 6 }}>
            {[
              ['mon · 9 am', 'standup — pre-write sun 5pm?'],
              ['sun · 9 pm', 'Iris: what\'s the dread?'],
            ].map(([when, what], i) => (
              <div key={i} className="row" style={{ gap: 8, alignItems: 'baseline' }}>
                <span style={{ width: 80, fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>{when}</span>
                <span style={{ fontSize: 12, color: 'var(--ink)' }}>{what}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="row" style={{ justifyContent: 'space-between', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.06em', textTransform: 'uppercase', padding: '12px 56px 24px', borderTop: '1px solid var(--line-soft)' }}>
        <span>compiled by iris · 2:00 am sun → mon</span>
        <span>reviewed by you · — not yet —</span>
      </div>
    </div>
  );
}

window.ReviewScreen = ReviewScreen;

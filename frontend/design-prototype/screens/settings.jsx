// screens/settings.jsx — "What Iris knows about you"

const IRIS_KNOWS = [
  { fact: "I work in design. Lead level. Joel is my manager.",                       since: '47d', source: 'chat'    },
  { fact: "I live in Oakland. My partner is M. We hike together.",                   since: '43d', source: 'journal' },
  { fact: "My standup is Tuesdays at 9. It often runs over.",                         since: '38d', source: 'pattern' },
  { fact: "Sleep below 6.5h makes my next-day mood drop ~1.2 points.",                since: '21d', source: 'derived' },
  { fact: "My HRV baseline is 47 ms. Below 40 — I feel it before I see it.",          since: '18d', source: 'air'    },
  { fact: "I describe relief in my shoulders. I describe dread in my jaw.",           since: '17d', source: 'language' },
  { fact: "My body recovers faster than my words admit (gap avg +28).",               since: '12d', source: 'fusion' },
  { fact: "Mom has an appointment coming up. I haven't called her in 9 days.",        since: '5d',  source: 'chat'    },
  { fact: "I want to go somewhere in August. We haven't decided.",                    since: '12d', source: 'journal' },
];

const SOURCES = [
  { name: 'Fitbit Air',       state: 'connected', detail: 'paired apr 14 · 24/7 · 71% battery', icon: '◉', featured: true },
  { name: 'Google Health',    state: 'connected', detail: 'cardio load, readiness, AFib watch', icon: '✚' },
  { name: 'Calendar',         state: 'connected', detail: 'titles only · no body', icon: '▦' },
  { name: 'Spotify',          state: 'connected', detail: 'listening mood (private)', icon: '♪' },
  { name: 'Photos',           state: 'paused',    detail: 'scene + faces, on-device', icon: '◧' },
  { name: 'Messages',         state: 'off',       detail: 'never. by design.',       icon: '✉' },
  { name: 'Location',         state: 'off',       detail: 'home/work radius only',   icon: '⌖' },
];

function SettingsScreen({ go }) {
  return (
    <div className="col" style={{ padding: '32px 56px 48px', gap: 28 }}>
      <header className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid var(--line)', paddingBottom: 18 }}>
        <div className="col" style={{ gap: 6 }}>
          <div className="kicker">settings · what iris knows</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
            The shape of you,<br /><span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>so far.</span>
          </h1>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn" onClick={() => go && go('onboarding')}>↺ re-meet iris</button>
          <button className="btn">export everything</button>
          <button className="btn" style={{ color: 'var(--rose)', borderColor: 'var(--rose)' }}>delete & forget</button>
        </div>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 32 }}>
        {/* Iris's notes about you */}
        <section className="col" style={{ gap: 16 }}>
          <div className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between' }}>
            <div>
              <div className="kicker">iris's stable notes about you</div>
              <h2 className="serif" style={{ margin: '4px 0 0', fontSize: 24 }}>What I've come to know.</h2>
            </div>
            <span className="tag">{IRIS_KNOWS.length} facts · editable</span>
          </div>
          <div className="col" style={{ gap: 4 }}>
            {IRIS_KNOWS.map((k, i) => (
              <div key={i} style={{
                display: 'grid', gridTemplateColumns: '1fr 80px 90px',
                gap: 16, padding: '14px 0', alignItems: 'baseline',
                borderTop: i === 0 ? 'none' : '1px solid var(--line-soft)',
              }}>
                <span className="serif" style={{ fontSize: 17, lineHeight: 1.4, color: 'var(--ink)', fontStyle: 'italic' }}>
                  "{k.fact}"
                </span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)', letterSpacing: '0.06em' }}>{k.source}</span>
                <div className="row" style={{ gap: 6, justifyContent: 'flex-end' }}>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)' }}>{k.since}</span>
                  <button className="btn ghost" style={{ fontSize: 11, color: 'var(--ink-3)' }} aria-label="edit">↗</button>
                  <button className="btn ghost" style={{ fontSize: 11, color: 'var(--rose)' }} aria-label="forget">×</button>
                </div>
              </div>
            ))}
          </div>
          <button className="btn" style={{ alignSelf: 'flex-start', marginTop: 4 }}>+ tell iris something new</button>
        </section>

        {/* Right column — sources + privacy */}
        <aside className="col" style={{ gap: 24 }}>
          <section>
            <div className="kicker">data sources</div>
            <h2 className="serif" style={{ margin: '4px 0 14px', fontSize: 24 }}>Where iris looks.</h2>
            <div className="col" style={{ gap: 8 }}>
              {SOURCES.map((s, i) => (
                <div key={i} className="row" style={{
                  alignItems: 'center', gap: 14, padding: '10px 12px',
                  background: s.featured ? 'rgba(169,200,163,0.06)' : 'var(--bg-2)',
                  border: '1px solid ' + (s.featured ? 'var(--sage-dim)' : 'var(--line-soft)'),
                  borderRadius: 8,
                }}>
                  <span style={{ width: 24, color: s.featured ? 'var(--sage)' : 'var(--ink-3)', fontFamily: 'var(--serif)', fontSize: 16 }}>{s.icon}</span>
                  <div className="col" style={{ flex: 1, gap: 1 }}>
                    <span style={{ fontSize: 13, color: 'var(--ink)' }}>{s.name}{s.featured && <span style={{ marginLeft: 8, fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--sage)', letterSpacing: '0.1em' }}>PRIMARY BIOSIGNAL</span>}</span>
                    <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>{s.detail}</span>
                  </div>
                  <span style={{
                    fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase',
                    color: s.state === 'connected' ? 'var(--sage)' : s.state === 'paused' ? 'var(--amber)' : 'var(--ink-4)',
                  }}>
                    {s.state === 'connected' && '● on'}
                    {s.state === 'paused' && '◐ paused'}
                    {s.state === 'off' && '○ off'}
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section>
            <div className="kicker">how iris talks</div>
            <div className="col" style={{ gap: 8, marginTop: 10 }}>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', padding: '12px 14px', border: '1px solid var(--line)', borderRadius: 8 }}>
                <span style={{ fontSize: 13 }}>Daily check-in</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-3)' }}>7:30 pm</span>
              </div>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', padding: '12px 14px', border: '1px solid var(--line)', borderRadius: 8 }}>
                <span style={{ fontSize: 13 }}>Sunday review</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-3)' }}>9:00 am</span>
              </div>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', padding: '12px 14px', border: '1px solid var(--line)', borderRadius: 8 }}>
                <span style={{ fontSize: 13 }}>Insight nudges</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--sage)' }}>at most 1/day</span>
              </div>
            </div>
          </section>

          <section style={{ padding: '16px 18px', border: '1px solid var(--line-soft)', borderRadius: 10, background: 'var(--bg-2)' }}>
            <div className="row" style={{ gap: 10, alignItems: 'center', marginBottom: 8 }}>
              <div className="iris-orb sm" />
              <span className="kicker">iris's note</span>
            </div>
            <div className="serif ital" style={{ fontSize: 15, lineHeight: 1.4, color: 'var(--ink-2)' }}>
              "Everything I know about you lives on this device. If you ever want me to forget — half, or all — that is a button. Not a conversation."
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

window.SettingsScreen = SettingsScreen;

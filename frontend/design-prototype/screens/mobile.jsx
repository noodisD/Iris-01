// screens/mobile.jsx — Iris on the go (companion phone view, in a bezel)

function PhoneBezel({ children, dark = true, time = '7:42' }) {
  const W = 340, H = 720;
  return (
    <div style={{
      width: W, height: H,
      borderRadius: 50, padding: 6,
      background: 'linear-gradient(135deg, #1a1a14, #2a2a22, #1a1a14)',
      boxShadow: '0 0 0 1.5px #3a3a30, 0 30px 60px -20px rgba(0,0,0,0.6), 0 0 0 2px #060606',
      position: 'relative', flexShrink: 0,
    }}>
      <div style={{
        width: '100%', height: '100%', borderRadius: 44,
        background: '#0a0a08', overflow: 'hidden', position: 'relative',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Notch / Dynamic Island */}
        <div style={{
          position: 'absolute', top: 10, left: '50%', transform: 'translateX(-50%)',
          width: 100, height: 28, borderRadius: 999, background: '#000', zIndex: 5,
        }} />
        {/* Status bar */}
        <div className="row" style={{
          padding: '14px 22px 6px', justifyContent: 'space-between',
          alignItems: 'center', fontFamily: 'var(--sans)', fontSize: 14, color: 'var(--ink)',
          fontWeight: 600, position: 'relative', zIndex: 10,
        }}>
          <span style={{ letterSpacing: '-0.01em' }}>{time}</span>
          <span style={{ width: 100 }} />
          <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink)' }}>● ● ●</span>
        </div>
        {children}
        {/* Home indicator */}
        <div style={{
          position: 'absolute', bottom: 8, left: '50%', transform: 'translateX(-50%)',
          width: 130, height: 4, borderRadius: 999, background: 'rgba(255,255,255,0.5)',
        }} />
      </div>
    </div>
  );
}

// ───────── Phone screen contents

function MobileToday() {
  return (
    <div className="col" style={{ flex: 1, padding: '12px 18px 32px', overflow: 'hidden' }}>
      <div className="row" style={{ alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <div className="iris-orb sm" />
        <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink-3)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>iris · 7:42 pm</span>
      </div>
      <h1 className="serif" style={{ fontSize: 32, lineHeight: 0.95, margin: '8px 0 6px', letterSpacing: '-0.02em', color: 'var(--ink)' }}>
        How's tonight,<br /><span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>really?</span>
      </h1>
      <div style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 18 }}>Tap any to start.</div>

      <div className="col" style={{ gap: 6, marginBottom: 18 }}>
        {['Three lines, please', 'Just chat', "I'm tired"].map((q, i) => (
          <button key={i} style={{
            background: 'rgba(169,200,163,0.08)', border: '1px solid var(--sage-dim)',
            color: 'var(--sage)', padding: '11px 14px', borderRadius: 10,
            textAlign: 'left', fontFamily: 'inherit', fontSize: 13, cursor: 'pointer',
          }}>{q}</button>
        ))}
      </div>

      {/* Body / Words mini card */}
      <div style={{
        background: 'var(--bg-2)', border: '1px solid var(--line-soft)', borderRadius: 14,
        padding: '14px 16px', marginBottom: 14,
      }}>
        <div className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8 }}>
          <span className="kicker">body · air</span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 8, color: 'var(--ink-4)', letterSpacing: '0.08em' }}>● 4 MIN AGO</span>
        </div>
        <div className="row" style={{ alignItems: 'baseline', gap: 14 }}>
          <div className="col">
            <span className="numerals" style={{ fontSize: 30, color: 'var(--sage)', lineHeight: 1 }}>72</span>
            <span style={{ fontSize: 9, color: 'var(--ink-3)', fontFamily: 'var(--mono)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>readiness</span>
          </div>
          <div className="col">
            <span className="numerals" style={{ fontSize: 30, color: 'var(--amber)', lineHeight: 1 }}>38</span>
            <span style={{ fontSize: 9, color: 'var(--ink-3)', fontFamily: 'var(--mono)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>words</span>
          </div>
          <div className="col">
            <span className="numerals" style={{ fontSize: 30, color: 'var(--ink)', lineHeight: 1 }}>+34</span>
            <span style={{ fontSize: 9, color: 'var(--ink-3)', fontFamily: 'var(--mono)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>gap</span>
          </div>
        </div>
        <div style={{ fontSize: 11, color: 'var(--ink-2)', fontStyle: 'italic', marginTop: 8, lineHeight: 1.45 }}>
          "Your body has more in the tank than your words say."
        </div>
      </div>

      {/* Habits today — minimal row */}
      <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-soft)', borderRadius: 14, padding: '12px 14px' }}>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
          <span className="kicker">today's 5</span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--sage)' }}>3 / 5</span>
        </div>
        <div className="col" style={{ gap: 8 }}>
          {[
            ['Meditate', true, 'var(--sage)'],
            ['Walk', true, 'var(--amber)'],
            ['Water early', true, 'var(--sage)'],
            ['Read · 20 pages', false, 'var(--indigo)'],
            ['No phone in bed', false, 'var(--rose)'],
          ].map(([n, done, c], i) => (
            <div key={i} className="row" style={{ alignItems: 'center', gap: 10 }}>
              <span style={{
                width: 16, height: 16, borderRadius: '50%',
                border: '1.5px solid ' + (done ? c : 'var(--line)'),
                background: done ? c : 'transparent',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#14140f', fontSize: 9,
              }}>{done && '✓'}</span>
              <span style={{ fontSize: 13, color: done ? 'var(--ink)' : 'var(--ink-2)', flex: 1 }}>{n}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MobileNudge() {
  // Lock-screen / notification view
  return (
    <div className="col" style={{
      flex: 1,
      background: 'linear-gradient(180deg, #050504 0%, #0e0e0c 50%, #050504 100%)',
      padding: '60px 18px 32px', overflow: 'hidden', position: 'relative',
    }}>
      {/* big time */}
      <div className="col" style={{ alignItems: 'center', marginBottom: 38 }}>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>tuesday · may 27</span>
        <span style={{ fontFamily: 'var(--serif)', fontSize: 88, color: 'var(--ink)', lineHeight: 1, letterSpacing: '-0.04em', marginTop: 4 }}>7:42</span>
      </div>

      {/* The nudge — a Iris notification */}
      <div style={{
        background: 'rgba(20,20,16,0.75)',
        backdropFilter: 'blur(20px)',
        border: '1px solid rgba(169,200,163,0.25)',
        borderRadius: 22,
        padding: '14px 16px',
        marginBottom: 12,
      }}>
        <div className="row" style={{ alignItems: 'flex-start', gap: 10 }}>
          <div className="iris-orb sm" style={{ marginTop: 4 }} />
          <div className="col" style={{ flex: 1, gap: 4 }}>
            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--ink-2)', fontWeight: 500 }}>IRIS</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink-3)' }}>now</span>
            </div>
            <div className="serif ital" style={{ fontSize: 14, color: 'var(--ink)', lineHeight: 1.4 }}>
              "Your design review just shipped. Your HRV agrees. Three lines about today?"
            </div>
          </div>
        </div>
      </div>

      {/* Body alert */}
      <div style={{
        background: 'rgba(20,20,16,0.75)', backdropFilter: 'blur(20px)',
        border: '1px solid rgba(255,255,255,0.06)', borderRadius: 22, padding: '12px 16px',
      }}>
        <div className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 6 }}>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--sage)', letterSpacing: '0.1em' }}>● FITBIT AIR</span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink-3)' }}>5m ago</span>
        </div>
        <div style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.45 }}>
          HRV climbing — body recovering well. Sleep window starts at 10:30.
        </div>
      </div>

      <div style={{ flex: 1 }} />

      <div className="col" style={{ alignItems: 'center', gap: 6 }}>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink-4)', letterSpacing: '0.1em' }}>SWIPE UP TO TALK</span>
      </div>
    </div>
  );
}

function MobileQuickChat() {
  // Quick chat view
  return (
    <div className="col" style={{ flex: 1, padding: '14px 18px 18px', overflow: 'hidden' }}>
      <div className="row" style={{ alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <span style={{ fontSize: 13, color: 'var(--ink-3)' }}>‹</span>
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <div className="iris-orb sm" />
          <span className="serif ital" style={{ fontSize: 16, color: 'var(--ink)' }}>Iris</span>
        </div>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)' }}>•••</span>
      </div>

      <div className="col" style={{ flex: 1, gap: 14, overflow: 'auto' }}>
        <div className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
          <div className="iris-orb sm" style={{ marginTop: 4 }} />
          <div className="serif ital" style={{ fontSize: 15, color: 'var(--ink)', lineHeight: 1.4, maxWidth: 220 }}>
            "Just a quick one — where do you feel today, in your body?"
          </div>
        </div>

        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <div style={{ background: 'var(--bg-2)', padding: '8px 12px', borderRadius: 14, fontSize: 13, color: 'var(--ink-2)', maxWidth: 220 }}>
            shoulders, a little. mostly tired.
          </div>
        </div>

        <div className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
          <div className="iris-orb sm" style={{ marginTop: 4 }} />
          <div className="col" style={{ gap: 6 }}>
            <div className="serif ital" style={{ fontSize: 15, color: 'var(--ink)', lineHeight: 1.4, maxWidth: 220 }}>
              "Shoulders — that's been your relief word lately. Good sign."
            </div>
            <div style={{
              fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--sage)',
              borderBottom: '1px dotted var(--sage-dim)', alignSelf: 'flex-start', paddingBottom: 1,
            }}>shoulders = relief × 5</div>
          </div>
        </div>
      </div>

      <div className="row" style={{ gap: 6, paddingTop: 12, alignItems: 'center' }}>
        <div style={{
          flex: 1, background: 'var(--bg-2)', border: '1px solid var(--line)',
          borderRadius: 999, padding: '8px 14px', fontSize: 12, color: 'var(--ink-3)',
        }}>say more…</div>
        <div style={{
          width: 32, height: 32, borderRadius: '50%', background: 'var(--sage)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 14, color: '#14140f',
        }}>↑</div>
      </div>
    </div>
  );
}

function MobileScreen() {
  return (
    <div className="col" style={{ padding: '24px 56px 48px', gap: 24, minHeight: '100%' }}>
      <header className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid var(--line)', paddingBottom: 18 }}>
        <div className="col" style={{ gap: 6 }}>
          <div className="kicker">on the go · iris on your phone</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
            Three moments,<br /><span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>one companion.</span>
          </h1>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn">↓ download for iOS</button>
          <button className="btn">↓ Android</button>
        </div>
      </header>

      <p style={{ margin: 0, fontSize: 15, lineHeight: 1.55, color: 'var(--ink-2)', maxWidth: 720, fontFamily: 'var(--serif)' }}>
        The phone app is where Iris lives between desktop sessions — a soft prompt at the right hour, a glance at the body, a few lines when you have a minute. Same memory, fewer charts.
      </p>

      {/* Three phones */}
      <div className="row" style={{ gap: 56, justifyContent: 'center', padding: '20px 0', alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div className="col" style={{ alignItems: 'center', gap: 18 }}>
          <PhoneBezel>
            <MobileNudge />
          </PhoneBezel>
          <div className="col" style={{ alignItems: 'center', gap: 4, maxWidth: 280 }}>
            <span className="kicker">i. the nudge</span>
            <span className="serif ital" style={{ fontSize: 16, color: 'var(--ink-2)', textAlign: 'center', lineHeight: 1.4 }}>
              A gentle notification at the right hour. Iris knows when to ask.
            </span>
          </div>
        </div>

        <div className="col" style={{ alignItems: 'center', gap: 18 }}>
          <PhoneBezel>
            <MobileToday />
          </PhoneBezel>
          <div className="col" style={{ alignItems: 'center', gap: 4, maxWidth: 280 }}>
            <span className="kicker">ii. the glance</span>
            <span className="serif ital" style={{ fontSize: 16, color: 'var(--ink-2)', textAlign: 'center', lineHeight: 1.4 }}>
              Body, words, habits — at a glance. No dashboards. One screen, one truth.
            </span>
          </div>
        </div>

        <div className="col" style={{ alignItems: 'center', gap: 18 }}>
          <PhoneBezel>
            <MobileQuickChat />
          </PhoneBezel>
          <div className="col" style={{ alignItems: 'center', gap: 4, maxWidth: 280 }}>
            <span className="kicker">iii. the check-in</span>
            <span className="serif ital" style={{ fontSize: 16, color: 'var(--ink-2)', textAlign: 'center', lineHeight: 1.4 }}>
              A few sentences from anywhere. Pairs with the Air on your wrist.
            </span>
          </div>
        </div>
      </div>

      {/* Air watch face callout */}
      <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 32, padding: '32px 24px', background: 'var(--bg-2)', border: '1px solid var(--line-soft)', borderRadius: 12 }}>
        <div className="col" style={{ gap: 10 }}>
          <span className="kicker">on your wrist</span>
          <h3 className="serif" style={{ margin: 0, fontSize: 28, lineHeight: 1.1, letterSpacing: '-0.02em' }}>
            Iris reads the Air, all day, on device.
          </h3>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.55, maxWidth: 380 }}>
            HRV, breath, RHR, sleep stages, skin temp variation, AFib watching. Raw data stays on the Air and phone. Iris only ever sees summaries.
          </p>
          <div className="row" style={{ gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
            <span className="tag">paired apr 14</span>
            <span className="tag">battery 71%</span>
            <span className="tag" style={{ color: 'var(--sage)', borderColor: 'var(--sage-dim)' }}>● syncing</span>
          </div>
        </div>
        <div className="col" style={{ alignItems: 'center', justifyContent: 'center' }}>
          {/* Stylized Air pebble */}
          <svg width="220" height="160" viewBox="0 0 220 160">
            <defs>
              <radialGradient id="airpb" cx="40%" cy="35%" r="60%">
                <stop offset="0%" stopColor="#2a2a22" />
                <stop offset="60%" stopColor="#1a1a14" />
                <stop offset="100%" stopColor="#0d0d0a" />
              </radialGradient>
              <radialGradient id="airglow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="var(--sage)" stopOpacity="0.85" />
                <stop offset="60%" stopColor="var(--sage)" stopOpacity="0.4" />
                <stop offset="100%" stopColor="var(--sage)" stopOpacity="0" />
              </radialGradient>
            </defs>
            <rect x="35" y="40" width="150" height="80" rx="40" fill="url(#airpb)" stroke="var(--line)" />
            <circle cx="110" cy="80" r="30" fill="url(#airglow)" />
            <circle cx="110" cy="80" r="6" fill="var(--sage)" />
            <circle cx="110" cy="80" r="2" fill="#0a0a06" />
            <text x="110" y="148" textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-3)" letterSpacing="0.12em">FITBIT AIR · 12G</text>
          </svg>
        </div>
      </section>

      <div className="row" style={{ justifyContent: 'space-between', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
        <span>iris mobile · v.0.6 · ios + android</span>
        <span>same memory · everywhere · always private</span>
      </div>
    </div>
  );
}

window.MobileScreen = MobileScreen;

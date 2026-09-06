// app.jsx — Iris app shell, sidebar nav, routing
const { useState, useEffect } = React;

const NAV = [
  { id: 'chat',      label: 'Chat',       hint: 'Talk to Iris' },
  { id: 'dashboard', label: 'Today',      hint: 'At a glance' },
  { id: 'body',      label: 'Body',       hint: 'Signals from your Air' },
  { id: 'journal',   label: 'Journal',    hint: 'Write & reflect' },
  { id: 'habits',    label: 'Habits',     hint: 'Daily practice' },
  { id: 'insight',   label: 'Insights',   hint: 'Patterns Iris found' },
  { id: 'review',    label: 'Review',     hint: 'Weekly + monthly' },
  { id: 'mobile',    label: 'On the go',  hint: 'Iris on your phone' },
  { id: 'settings',  label: 'Settings',   hint: "What Iris knows" },
];

const SCREENS = {
  chat:       () => <ChatScreen />,
  dashboard:  () => <DashboardScreen />,
  body:       () => <BodyScreen />,
  journal:    () => <JournalScreen />,
  habits:     () => <HabitsScreen />,
  insight:    () => <InsightScreen />,
  review:     () => <ReviewScreen />,
  mobile:     () => <MobileScreen />,
  onboarding: () => <OnboardingScreen />,
  settings:   () => <SettingsScreen go={(id) => window.dispatchEvent(new CustomEvent('nav', { detail: id }))} />,
};

// Each screen has a default Iris "vibe" — what hue/breath rate her orb wears
const SCREEN_VIBE = {
  chat: 'calm', dashboard: 'calm', body: 'cool', journal: 'high', habits: 'high',
  insight: 'low', review: 'cool', mobile: 'calm', onboarding: 'high', settings: 'dim',
};

function Sidebar({ active, onNav, day }) {
  return (
    <aside data-screen-label="Sidebar" style={{
      width: 220, height: '100%', background: 'var(--bg-1)',
      borderRight: '1px solid var(--line-soft)',
      padding: '22px 0 18px',
      display: 'flex', flexDirection: 'column', flexShrink: 0,
    }}>
      <div className="row" style={{ alignItems: 'center', gap: 10, padding: '0 22px 22px' }}>
        <IrisOrb />
        <div className="col" style={{ gap: 1, lineHeight: 1 }}>
          <span className="serif" style={{ fontSize: 22, color: 'var(--ink)' }}>Iris</span>
          <span style={{ fontSize: 10, color: 'var(--ink-3)', fontFamily: 'var(--mono)', letterSpacing: '0.14em', textTransform: 'uppercase' }}>v.0 · day {day}</span>
        </div>
      </div>

      <hr className="hairline" style={{ margin: '0 22px' }} />

      <nav className="col" style={{ padding: '14px 12px', gap: 1, flex: 1 }}>
        {NAV.map(item => {
          const isActive = active === item.id;
          return (
            <button key={item.id}
              onClick={() => onNav(item.id)}
              style={{
                background: isActive ? 'var(--bg-2)' : 'transparent',
                border: 'none',
                color: isActive ? 'var(--ink)' : 'var(--ink-2)',
                textAlign: 'left',
                padding: '9px 12px',
                borderRadius: 6,
                fontFamily: 'var(--sans)',
                fontSize: 13,
                letterSpacing: '0.01em',
                cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 10,
                position: 'relative',
              }}
              onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.color = 'var(--ink)'; }}
              onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.color = 'var(--ink-2)'; }}
            >
              {isActive && <span style={{ position: 'absolute', left: -1, top: 8, bottom: 8, width: 2, background: 'var(--sage)', borderRadius: 2 }} />}
              <span style={{ flex: 1 }}>{item.label}</span>
              {item.id === 'insight' && <span className="dot sage" />}
              {item.id === 'body' && <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--sage)', letterSpacing: '0.06em' }}>● air</span>}
            </button>
          );
        })}
      </nav>

      <div style={{ padding: '12px 22px 4px' }}>
        <button onClick={() => onNav('onboarding')}
          style={{ background: 'none', border: 'none', color: 'var(--ink-3)', fontSize: 11, fontFamily: 'var(--mono)', letterSpacing: '0.08em', textTransform: 'uppercase', padding: 0, cursor: 'pointer', textAlign: 'left' }}>
          ↺ Re-meet Iris
        </button>
      </div>
      <div style={{ padding: '10px 22px 0', borderTop: '1px solid var(--line-soft)', marginTop: 6 }}>
        <div className="row" style={{ alignItems: 'center', gap: 10, marginTop: 12 }}>
          <div style={{
            width: 28, height: 28, borderRadius: '50%',
            background: 'linear-gradient(135deg, #d4a374, #c47d4a)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'var(--serif)', fontSize: 14, color: '#1a1a14',
          }}>S</div>
          <div className="col" style={{ gap: 1 }}>
            <span style={{ fontSize: 12, color: 'var(--ink)' }}>Sam Reeves</span>
            <span style={{ fontSize: 10, color: 'var(--ink-3)' }}>Pacific · 7:42 PM</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "#a9c8a3",
  "tone": "warm",
  "density": "balanced",
  "dayAge": 47,
  "orbVibe": "auto"
}/*EDITMODE-END*/;

const ACCENT_DIM = {
  '#a9c8a3': '#6f8c6a',
  '#d4a374': '#a07a55',
  '#9aa3d4': '#6f78a0',
  '#d48a8a': '#a06868',
};

function App() {
  const [active, setActive] = useState('chat');
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  useEffect(() => {
    const onNav = (e) => setActive(e.detail);
    window.addEventListener('nav', onNav);
    return () => window.removeEventListener('nav', onNav);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty('--sage', t.accent);
    root.style.setProperty('--sage-dim', ACCENT_DIM[t.accent] || '#6f8c6a');
  }, [t.accent]);

  // Publish global Iris state (day, tone, density, vibe) + drive CSS-var orb
  useEffect(() => {
    const vibe = t.orbVibe === 'auto' ? (SCREEN_VIBE[active] || 'calm') : t.orbVibe;
    window.__iris = { ...window.__iris, tone: t.tone, density: t.density };
    window.setIrisDay(Number(t.dayAge));
    window.setIrisVibe(vibe);
    const palettes = {
      calm: ['#d8efd2','#a9c8a3','#6f8c6a','rgba(169,200,163,0.35)','4s'],
      low:  ['#f3d4d4','#d48a8a','#a06868','rgba(212,138,138,0.40)','6.5s'],
      high: ['#f4dcb8','#d4a374','#a07a55','rgba(212,163,116,0.45)','2.4s'],
      cool: ['#dbe0f0','#9aa3d4','#6f78a0','rgba(154,163,212,0.35)','5.5s'],
      dim:  ['#3a3a30','#2a2a22','#1a1a14','rgba(80,76,64,0.30)','7s'],
    };
    const [a,b,c,g,r] = palettes[vibe] || palettes.calm;
    const root = document.documentElement;
    root.style.setProperty('--orb-hue-a', a);
    root.style.setProperty('--orb-hue-b', b);
    root.style.setProperty('--orb-hue-c', c);
    root.style.setProperty('--orb-glow', g);
    root.style.setProperty('--orb-rate', r);
  }, [t.tone, t.density, t.dayAge, t.orbVibe, active]);

  const Screen = SCREENS[active] || SCREENS.chat;
  const tabs = [
    { title: 'Iris · ' + (NAV.find(n => n.id === active)?.label || 'Welcome') },
    { title: 'Inbox · Gmail' },
    { title: 'Calendar' },
  ];

  return (
    <>
      <ChromeWindow
        tabs={tabs}
        activeIndex={0}
        url={`iris.app/${active === 'dashboard' ? 'today' : active}`}
        width={1400}
        height={900}
      >
        <div style={{ display: 'flex', height: '100%', background: 'var(--bg-0)' }}>
          <Sidebar active={active} onNav={setActive} day={t.dayAge} />
          <main data-screen-label={NAV.find(n => n.id === active)?.label || 'App'} style={{ flex: 1, overflow: 'auto', position: 'relative' }}>
            <Screen />
          </main>
        </div>
      </ChromeWindow>

      <TweaksPanel title="Tweaks">
        <TweakSection label="Look">
          <TweakColor label="Accent" value={t.accent}
            options={['#a9c8a3', '#d4a374', '#9aa3d4', '#d48a8a']}
            onChange={v => setTweak('accent', v)} />
          <TweakSelect label="Density" value={t.density}
            options={['sparse','balanced','dense']}
            onChange={v => setTweak('density', v)} />
        </TweakSection>
        <TweakSection label="Iris">
          <TweakRadio label="Tone" value={t.tone}
            options={['clinical','warm','playful']}
            onChange={v => setTweak('tone', v)} />
          <TweakSelect label="Day in journey" value={String(t.dayAge)}
            options={['1','7','47']}
            onChange={v => setTweak('dayAge', Number(v))} />
          <TweakSelect label="Orb vibe" value={t.orbVibe}
            options={['auto','calm','low','high','cool','dim']}
            onChange={v => setTweak('orbVibe', v)} />
        </TweakSection>
        <TweakSection label="Jump to screen">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            {Object.keys(SCREENS).map(s => (
              <TweakButton key={s} label={s} secondary onClick={() => setActive(s)} />
            ))}
          </div>
        </TweakSection>
      </TweaksPanel>
    </>
  );
}

window.__iris = { tone: 'warm', density: 'dense' };

ReactDOM.createRoot(document.getElementById('root')).render(<App />);

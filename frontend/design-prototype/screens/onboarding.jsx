// screens/onboarding.jsx — Conversational onboarding (Iris's first chat with you)

const ONBOARD_SCRIPT = [
  { who: 'iris', text: "Hi. I'm Iris." },
  { who: 'iris', text: "Before we start, I want to be clear about three things — and then we'll just talk." },
  { who: 'iris', text: "One: I live on this device. Nothing leaves it unless you tell me to.", noticed: 'private by default' },
  { who: 'iris', text: "Two: I'm slow at first. I won't have much to say for a week or two. I'm listening." },
  { who: 'iris', text: "Three: every thing I remember about you is editable. Forgetting is a button.", noticed: 'editable memory' },
  { who: 'iris', text: "Ready when you are.", quick: [{ label: "Yes — let's start", next: 1 }] },
];

const ONBOARD_BRANCHES = [
  // step 0: intro (above)
  null,
  // step 1: name + what to call you
  {
    setup: [
      { who: 'iris', text: "First — what should I call you?", input: 'name' },
    ],
    onAnswer: (answers) => ([
      { who: 'me', text: answers.name || 'Sam' },
      { who: 'iris', text: `Nice to meet you, ${answers.name || 'Sam'}.` },
      { who: 'iris', text: "Now — what brought you here? You can give me a sentence, or just a few words. There's no wrong answer.", input: 'reason', placeholder: 'Anything — a feeling, a goal, a question…' },
    ]),
  },
  // step 2: reason + reflect
  {
    onAnswer: (answers) => ([
      { who: 'me', text: answers.reason || "I'm tired of carrying everything in my head" },
      { who: 'iris', text: "Thank you. I'll hold that gently while we get to know each other." , noticed: 'starting reason' },
      { who: 'iris', text: "Here's how I want to learn the texture of your days. I'll ask three small questions a day to start — usually morning and evening. You can ignore me whenever. Sound okay?", quick: [{ label: "Sounds okay", next: 3 }, { label: "Once a day, please", next: 3, answer: 'once_a_day' }] },
    ]),
  },
  // step 3: pick threads
  {
    setup: [
      { who: 'iris', text: "Last big choice — what would you like me to listen for?" },
      { who: 'iris', text: "Pick what feels right today. None of this is permanent.", picker: 'threads' },
    ],
    onAnswer: (answers) => {
      const picked = (answers.threads || []).filter(Boolean);
      const list = picked.length ? picked.slice(0, 3).join(', ') + (picked.length > 3 ? '…' : '') : 'mood';
      return [
        { who: 'me', text: `${picked.length || 1} threads: ${list}` },
        { who: 'iris', text: `Got it. ${picked.length || 1} threads. I'll learn mood and energy first; the rest will start filling in.`, noticed: list },
        { who: 'iris', text: "One more thing — I work best when I can read your body, not just your words. Do you have a Fitbit Air?", quick: [{ label: "Yes — pair it now", next: 4, answer: { fitbit: 'pair' } }, { label: "Not yet — skip", next: 4, answer: { fitbit: 'skip' } }, { label: "I use Apple Health", next: 4, answer: { fitbit: 'apple' } }] },
      ];
    },
  },
  // step 4: fitbit
  {
    onAnswer: (answers) => {
      const f = answers.fitbit;
      if (f === 'pair') return [
        { who: 'me', text: "Pair it" },
        { who: 'iris', text: "Looking for your Air…", bio: { status: 'searching · 12 ft' } },
        { who: 'iris', text: "Found it. Paired. I'll start watching tonight — HRV, sleep stages, breath, RHR. AFib check runs in the background.", bio: { status: 'paired · 71% battery · 5d left' }, noticed: 'fitbit air paired' },
        { who: 'iris', text: "That's everything I need to begin. Are you ready?", quick: [{ label: "Yes — write my first three lines", next: 5 }, { label: "Just chat with me first", next: 5, answer: 'chat' }] },
      ];
      if (f === 'apple') return [
        { who: 'me', text: "I use Apple Health" },
        { who: 'iris', text: "I can read from Apple Health too — sleep, HRV, steps. (A Fitbit Air would give me more nuance, but this works.)" },
        { who: 'iris', text: "Ready to write your first three lines?", quick: [{ label: "Yes", next: 5 }, { label: "Chat first", next: 5, answer: 'chat' }] },
      ];
      return [
        { who: 'me', text: "Skip for now" },
        { who: 'iris', text: "No problem. I'll learn from your words first. You can connect a wearable anytime in settings." },
        { who: 'iris', text: "Ready to write your first three lines?", quick: [{ label: "Yes", next: 5 }, { label: "Chat first", next: 5, answer: 'chat' }] },
      ];
    },
  },
  // step 5: complete
  {
    setup: [
      { who: 'iris', text: "One more thing before we start — here's what I'll remember from this conversation.", review: true },
      { who: 'iris', text: "You can edit or remove any of this anytime in settings. Let's go." },
    ],
  },
];

const THREADS = [
  { key: 'mood',     label: 'mood & emotions' },
  { key: 'energy',   label: 'energy' },
  { key: 'sleep',    label: 'sleep' },
  { key: 'habits',   label: 'habits' },
  { key: 'topics',   label: 'what i talk about' },
  { key: 'worries',  label: 'worries i\'m carrying' },
  { key: 'wins',     label: 'wins & gratitude' },
  { key: 'social',   label: 'social connection' },
  { key: 'focus',    label: 'focus & flow' },
  { key: 'meals',    label: 'meals & meds' },
];

function OnboardBubble({ msg }) {
  if (msg.who === 'iris') {
    return (
      <div className="row" style={{ gap: 14, alignItems: 'flex-start', maxWidth: 600, marginBottom: 22, animation: 'fadeUp 0.4s ease' }}>
        <div className="iris-orb sm" style={{ marginTop: 6 }} />
        <div className="col" style={{ gap: 8 }}>
          <div className="serif" style={{ fontStyle: 'italic', fontSize: 22, lineHeight: 1.35, color: 'var(--ink)' }}>{msg.text}</div>
          {msg.noticed && (
            <div className="row" style={{ gap: 6, alignItems: 'baseline' }}>
              <span className="kicker" style={{ color: 'var(--ink-4)' }}>Noticed</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--sage)', borderBottom: '1px dotted var(--sage-dim)', paddingBottom: 1 }}>{msg.noticed}</span>
            </div>
          )}
          {msg.bio && (
            <div className="row" style={{ gap: 14, padding: '8px 12px', border: '1px dashed var(--sage-dim)', borderRadius: 6, alignItems: 'center', width: 'fit-content' }}>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--sage)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>● fitbit air</span>
              {Object.entries(msg.bio).map(([k, v], i) => (
                <span key={i} style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-2)' }}>{v}</span>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }
  return (
    <div className="row" style={{ justifyContent: 'flex-end', marginBottom: 22, animation: 'fadeUp 0.4s ease' }}>
      <div style={{
        background: 'var(--bg-2)', border: '1px solid var(--line-soft)', color: 'var(--ink-2)',
        padding: '10px 14px', borderRadius: 12, maxWidth: 460, fontSize: 14, lineHeight: 1.55,
      }}>{msg.text}</div>
    </div>
  );
}

function OnboardingScreen() {
  const [messages, setMessages] = React.useState(ONBOARD_SCRIPT);
  const [step, setStep] = React.useState(0);
  const [answers, setAnswers] = React.useState({});
  const [draft, setDraft] = React.useState('');
  const [pickedThreads, setPickedThreads] = React.useState(['mood','energy','sleep','habits','topics','wins']);
  const [thinking, setThinking] = React.useState(false);
  const scrollRef = React.useRef(null);

  React.useEffect(() => {
    if (scrollRef.current) {
      const el = scrollRef.current;
      requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
    }
  }, [messages, thinking]);

  const advance = (toStep, extraAnswer) => {
    const branch = ONBOARD_BRANCHES[toStep];
    if (!branch) return;
    const newAnswers = extraAnswer && typeof extraAnswer === 'object' ? { ...answers, ...extraAnswer } : answers;
    setAnswers(newAnswers);
    setStep(toStep);
    setThinking(true);
    setTimeout(() => {
      setThinking(false);
      const setup = branch.setup ? branch.setup : [];
      setMessages(prev => [...prev, ...setup]);
    }, 700);
  };

  const submitInput = () => {
    const branch = ONBOARD_BRANCHES[step];
    if (!branch) return;
    const lastInputField = [...(branch.setup || [])].reverse().find(m => m.input)?.input || 'reason';
    const newAnswers = { ...answers, [lastInputField]: draft.trim() };
    setAnswers(newAnswers);
    setDraft('');
    const nextBatch = branch.onAnswer ? branch.onAnswer(newAnswers) : [];
    setMessages(prev => [...prev, ...nextBatch]);
  };

  const submitQuick = (q) => {
    const branch = ONBOARD_BRANCHES[step];
    if (!branch) return;
    if (typeof q.answer === 'object') {
      const nextStep = q.next;
      advance(nextStep, q.answer);
      return;
    }
    if (q.next !== undefined) {
      setMessages(prev => [...prev, { who: 'me', text: q.label }]);
      setTimeout(() => advance(q.next, q.answer ? { [step === 4 ? 'fitbit' : 'choice']: q.answer } : null), 200);
      return;
    }
  };

  const submitThreads = () => {
    const newAnswers = { ...answers, threads: pickedThreads };
    setAnswers(newAnswers);
    const nextBatch = ONBOARD_BRANCHES[step].onAnswer(newAnswers);
    setMessages(prev => [...prev, ...nextBatch]);
  };

  // What input UI to render right now (based on the most recent Iris message)
  const lastIris = [...messages].reverse().find(m => m.who === 'iris');
  const showInput = lastIris && lastIris.input;
  const showQuick = lastIris && lastIris.quick && !showInput;
  const showPicker = lastIris && lastIris.picker === 'threads';
  const showReview = lastIris && lastIris.review;

  return (
    <div style={{ display: 'flex', height: '100%', background: 'var(--bg-0)' }}>
      {/* Left rail — minimal progress + reassurance */}
      <aside style={{ width: 280, padding: '40px 32px', borderRight: '1px dashed var(--line)' }}>
        <div className="row" style={{ gap: 12, alignItems: 'center', marginBottom: 24 }}>
          <div className="iris-orb lg" />
          <div className="col">
            <span className="serif" style={{ fontSize: 26, lineHeight: 1, color: 'var(--ink)' }}>Iris</span>
            <span style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--mono)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>day 0 · meeting you</span>
          </div>
        </div>

        <div className="col" style={{ gap: 10, paddingTop: 12 }}>
          <div className="kicker">where we are</div>
          {['Hello', 'Your name', 'Why you\'re here', 'What to listen for', 'Pair your body', 'A first promise'].map((label, i) => {
            const isActive = i === step;
            const isDone = i < step;
            return (
              <div key={i} className="row" style={{ gap: 10, alignItems: 'baseline', color: isActive ? 'var(--ink)' : isDone ? 'var(--ink-2)' : 'var(--ink-4)' }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: isDone ? 'var(--sage)' : isActive ? 'var(--sage)' : 'var(--ink-4)' }}>
                  {isDone ? '●' : isActive ? '◉' : '○'}
                </span>
                <span style={{ fontSize: 13 }}>{label}</span>
              </div>
            );
          })}
        </div>

        <hr className="dotline" style={{ margin: '28px 0 14px' }} />

        <div style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic', lineHeight: 1.6 }}>
          This is a conversation, not a form. Take as long as you want. You can leave and come back — I'll remember where we were.
        </div>
      </aside>

      {/* Conversation */}
      <main className="col" style={{ flex: 1, minWidth: 0 }}>
        <div ref={scrollRef} style={{ flex: 1, overflow: 'auto', padding: '56px 80px 24px' }}>
          <div className="col" style={{ maxWidth: 660, margin: '0 auto' }}>
            {step === 0 && (
              <>
                <div className="kicker" style={{ marginBottom: 14 }}>— day 0 · meeting Iris</div>
                <div className="serif" style={{ fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em', marginBottom: 38, color: 'var(--ink)' }}>
                  Let's <span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>begin</span>.
                </div>
              </>
            )}

            {messages.map((m, i) => <OnboardBubble key={i} msg={m} />)}

            {thinking && (
              <div className="row" style={{ gap: 14, alignItems: 'flex-start', maxWidth: 640, marginBottom: 22 }}>
                <div className="iris-orb sm" style={{ marginTop: 6 }} />
                <div className="row" style={{ gap: 4, alignItems: 'center', height: 30 }}>
                  {[0, 0.2, 0.4].map(d => (
                    <span key={d} style={{ width: 4, height: 4, borderRadius: 999, background: 'var(--sage)', animation: `blink 1.2s ease-in-out ${d}s infinite` }} />
                  ))}
                </div>
              </div>
            )}

            {showReview && (
              <div className="col" style={{ gap: 8, padding: '18px 20px', background: 'var(--bg-2)', border: '1px solid var(--line-soft)', borderRadius: 10, marginBottom: 22 }}>
                <div className="kicker">i will remember</div>
                {[
                  ['name', answers.name || 'Sam'],
                  ['reason for being here', answers.reason || 'I\'m tired of carrying everything in my head'],
                  ['threads to listen for', (answers.threads || pickedThreads).join(', ')],
                  ['body source', answers.fitbit === 'pair' ? 'Fitbit Air · paired' : answers.fitbit === 'apple' ? 'Apple Health' : 'words only'],
                ].map(([k, v], i) => (
                  <div key={i} className="row" style={{ alignItems: 'baseline', gap: 12 }}>
                    <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.08em', textTransform: 'uppercase', minWidth: 160 }}>{k}</span>
                    <span className="serif ital" style={{ fontSize: 16, color: 'var(--ink)' }}>"{v}"</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Composer area — adapts to what's needed */}
        <div style={{ padding: '14px 80px 36px', borderTop: '1px solid var(--line-soft)' }}>
          <div style={{ maxWidth: 660, margin: '0 auto' }}>
            {showPicker && (
              <div className="col" style={{ gap: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
                  {THREADS.map(t => {
                    const picked = pickedThreads.includes(t.key);
                    return (
                      <button key={t.key}
                        onClick={() => setPickedThreads(picked ? pickedThreads.filter(k => k !== t.key) : [...pickedThreads, t.key])}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 10,
                          padding: '10px 14px', borderRadius: 8, cursor: 'pointer',
                          background: picked ? 'rgba(169,200,163,0.08)' : 'transparent',
                          border: '1px solid ' + (picked ? 'var(--sage-dim)' : 'var(--line)'),
                          color: picked ? 'var(--ink)' : 'var(--ink-2)',
                          fontFamily: 'inherit', textAlign: 'left',
                        }}>
                        <span style={{
                          width: 14, height: 14, borderRadius: '50%', flexShrink: 0,
                          border: '1.5px solid ' + (picked ? 'var(--sage)' : 'var(--line)'),
                          background: picked ? 'var(--sage)' : 'transparent',
                        }} />
                        <span style={{ fontSize: 13 }}>{t.label}</span>
                      </button>
                    );
                  })}
                </div>
                <div className="row" style={{ justifyContent: 'flex-end' }}>
                  <button className="btn primary" onClick={submitThreads}>that's right →</button>
                </div>
              </div>
            )}

            {showQuick && !showPicker && (
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                {lastIris.quick.map((q, i) => (
                  <button key={i} className="btn" onClick={() => submitQuick(q)} style={{ borderColor: 'var(--sage-dim)', color: 'var(--sage)' }}>
                    {q.label}
                  </button>
                ))}
              </div>
            )}

            {showInput && !showPicker && (
              <div style={{
                background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 10,
                padding: '14px 16px', display: 'flex', alignItems: 'flex-end', gap: 12,
              }}>
                <textarea
                  value={draft}
                  onChange={e => setDraft(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitInput(); } }}
                  placeholder={lastIris.placeholder || 'Your turn…'}
                  rows={1}
                  style={{
                    flex: 1, background: 'transparent', border: 'none', resize: 'none',
                    color: 'var(--ink)', fontFamily: 'var(--sans)', fontSize: 14,
                    lineHeight: 1.5, outline: 'none', minHeight: 22,
                  }}
                />
                <button className="btn primary" onClick={submitInput}>Send</button>
              </div>
            )}

            {showReview && (
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                <button className="btn">edit any of this</button>
                <button className="btn primary" onClick={() => window.dispatchEvent(new CustomEvent('nav', { detail: 'chat' }))}>begin →</button>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

window.OnboardingScreen = OnboardingScreen;

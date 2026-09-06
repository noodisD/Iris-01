// screens/chat.jsx — Iris chat (state-driven, working send)
const { useState: useStateChat, useEffect: useEffectChat, useRef: useRefChat } = React;

// Scripted conversation trees per day-in-journey
const DAY_CONVOS = {
  1: [
    { who: 'iris', text: "Hello, Sam. It's nice to meet you." },
    { who: 'iris', text: "I won't have much to say at first — I'm mostly listening. Tell me about today, in whatever way feels easy.", quick: ["Today was hard", "Today was good", "I'm not sure why I'm here"] },
  ],
  7: [
    { who: 'iris', text: "A week in. The thing I'm starting to notice: you write longer entries on Saturday mornings. Anything to that?", quick: ["Saturdays are slow", "Coincidence I think", "Tell me what else you see"] },
    { who: 'me',   text: "i think they're just quieter" },
    { who: 'iris', text: "That makes sense. Quiet seems important to you — you've used the word four times this week.", noticed: ['quiet × 4'] },
    { who: 'iris', text: "What was today like?", quick: ["A bit tight", "Pretty good", "Tired"] },
  ],
  47: [
    { who: 'iris', kind: 'greet', text: "Welcome back, Sam. It's late — 7:42 on a Tuesday. How is the day landing in your body right now?" },
    { who: 'me',   text: "honestly kind of fried. the standup ran over and i didn't eat lunch until 3. been a long one." },
    { who: 'iris', kind: 'reflect', text: "That's the third Tuesday in a row standup has eaten through lunch. Last time you mentioned it the word you used was \"depleted.\" Same shape, or different today?" , noticed: ['tuesdays_standup', 'skipped_meals'] },
    { who: 'me',   text: "different. less anxious. just tired. i did get the design review done though, that was a relief" },
    { who: 'iris', kind: 'fusion', text: "Your Air agrees — your HRV is up 9ms from yesterday and your breathing rate quieted by 3 PM. The body knew the design review was over before you did.", bio: { hrv: '+9 ms', breath: '−0.8 br/min', rhr: 'steady' } },
    { who: 'iris', kind: 'celebrate', text: "Good. You'd been carrying that one for nine days." },
    { who: 'iris', kind: 'invite', text: "Want to log it as a win, or would you rather just sit with the tired for a minute and write three lines about the day?", quick: ["Log it as a win", "Three lines, please", "Ask me something else"] },
  ],
};

// Confidence-rated inferences shown in the right rail per day
const DAY_INFERRED = {
  1: [
    { tag: 'tone', value: 'guarded · curious', confidence: 0.42 },
    { tag: 'day', value: 'first conversation', confidence: 1 },
  ],
  7: [
    { tag: 'mood', value: 'steadying', confidence: 0.55 },
    { tag: 'rhythm', value: 'slow saturday mornings', confidence: 0.62 },
    { tag: 'vocab', value: 'quiet (×4), slow (×2)', confidence: 0.71 },
  ],
  47: [
    { tag: 'mood', value: 'tired · relieved', confidence: 0.84 },
    { tag: 'energy', value: '38 / 100 (you) · 72 (air)', confidence: 0.72 },
    { tag: 'meals', value: 'skipped lunch', confidence: 0.95 },
    { tag: 'pattern', value: 'tuesday standup overrun', confidence: 0.66 },
    { tag: 'win', value: 'design review shipped', confidence: 0.91 },
    { tag: 'hrv', value: '+9 ms post-3pm · air', confidence: 0.88 },
  ],
};

const DAY_HEADERS = {
  1:  { eyebrow: '— day 1 · meeting',       title1: "Tell me",     title2: "what today felt like" },
  7:  { eyebrow: '— day 7 · listening',     title1: "How are",     title2: "you tonight?" },
  47: { eyebrow: '— evening check-in',      title1: "How was today,", title2: "really?" },
};

function ChatMessage({ msg }) {
  if (msg.who === 'iris') {
    return (
      <div className="row" style={{ gap: 14, alignItems: 'flex-start', maxWidth: 640, marginBottom: 22, animation: 'fadeUp 0.4s ease' }}>
        <div className="iris-orb sm" style={{ marginTop: 6 }} />
        <div className="col" style={{ gap: 8 }}>
          <div className="serif" style={{
            fontStyle: 'italic', fontSize: 21, lineHeight: 1.35, color: 'var(--ink)', letterSpacing: '-0.005em',
          }}>{msg.text}</div>
          {msg.noticed && (
            <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
              <span className="kicker" style={{ color: 'var(--ink-4)' }}>Noticed</span>
              {msg.noticed.map((n, i) => (
                <span key={i} style={{
                  fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.04em',
                  color: 'var(--sage)', borderBottom: '1px dotted var(--sage-dim)', paddingBottom: 1,
                }}>{n}</span>
              ))}
            </div>
          )}
          {msg.bio && (
            <div className="row" style={{ gap: 14, marginTop: 4, padding: '8px 12px', border: '1px dashed var(--sage-dim)', borderRadius: 6, alignItems: 'center', width: 'fit-content' }}>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--sage)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>● from your air</span>
              {Object.entries(msg.bio).map(([k, v], i) => (
                <span key={i} style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-2)' }}>
                  <span style={{ color: 'var(--ink-4)' }}>{k}</span> {v}
                </span>
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
        padding: '10px 14px', borderRadius: 12, maxWidth: 460,
        fontSize: 14, lineHeight: 1.55, letterSpacing: '0.005em',
      }}>{msg.text}</div>
    </div>
  );
}

// Generate a Iris reply for a freeform user message based on tone + day
function generateIrisReply(userText, day, tone) {
  const text = userText.toLowerCase();
  const sayings = {
    warm: {
      tired: "Tired tracks. Want a soft landing tonight, or do you want me to ask you a real question?",
      anxious: "I'm here. Where do you feel it — chest, jaw, somewhere else?",
      good: "Hold onto that. What part of today made it feel that way?",
      idk: "That's okay. Sometimes a day just is. What did your hands do today?",
      default: "Mmm. Tell me more.",
    },
    clinical: {
      tired: "Noted: low-energy report. Sleep last night logged at 6h 51m. Possible factor.",
      anxious: "Noted: anxiety self-report. Cross-referencing HRV — give me a second.",
      good: "Positive affect logged. Adding to today's record.",
      idk: "Acknowledged. I'll wait.",
      default: "Acknowledged.",
    },
    playful: {
      tired: "Ugh, same energy. Tea or just collapse? 🍃",
      anxious: "I see you. Where's the brain holding it today?",
      good: "Yes! Tell me the thing.",
      idk: "Mood: indeterminate. Permitted. ✨",
      default: "Go on...",
    },
  };
  const t = sayings[tone] || sayings.warm;
  if (text.match(/tired|fried|exhausted|wiped|drained/)) return t.tired;
  if (text.match(/anxious|nervous|worried|scared|dread/)) return t.anxious;
  if (text.match(/good|great|nice|happy|relief|relieved/)) return t.good;
  if (text.match(/idk|don.t know|not sure|whatever/)) return t.idk;
  return t.default;
}

function InferredRail({ inferred, day }) {
  return (
    <aside style={{
      width: 280, flexShrink: 0, borderLeft: '1px dashed var(--line)',
      padding: '36px 24px 24px', background: 'transparent', overflow: 'auto',
    }}>
      <div className="kicker">From this conversation</div>
      <h3 className="serif" style={{ margin: '8px 0 18px', fontSize: 22, lineHeight: 1, color: 'var(--ink)' }}>
        {day === 1 ? "Iris is meeting you" : day === 7 ? "Iris is learning" : "Iris is hearing"}<span style={{ color: 'var(--sage)' }}>.</span>
      </h3>

      <div className="col" style={{ gap: 14 }}>
        {inferred.map((it, i) => (
          <div key={i} className="col" style={{ gap: 4 }}>
            <div className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between' }}>
              <span className="kicker" style={{ color: 'var(--ink-3)' }}>{it.tag}</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink-4)' }}>{Math.round(it.confidence * 100)}%</span>
            </div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink)', letterSpacing: '0.01em' }}>{it.value}</div>
            <div style={{ height: 1, background: 'var(--line-soft)', position: 'relative', marginTop: 2 }}>
              <div style={{ position: 'absolute', left: 0, top: 0, height: 1, width: `${it.confidence * 100}%`, background: 'var(--sage)' }} />
            </div>
          </div>
        ))}
      </div>

      <hr className="dotline" style={{ margin: '24px 0 18px' }} />

      <div className="col" style={{ gap: 8 }}>
        <div className="kicker">Will save to</div>
        <div className="col" style={{ gap: 5, fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-2)' }}>
          <div>→ today.journal</div>
          {day >= 7 && <div>→ mood.log</div>}
          {day >= 47 && <div>→ patterns.tuesday</div>}
          {day >= 47 && <div>→ wins.q2 (+1)</div>}
        </div>
      </div>

      <button className="btn" style={{ marginTop: 22, width: '100%' }}>Review before saving</button>
    </aside>
  );
}

function ChatScreen() {
  const { day } = useIrisState();
  const tone = (window.__iris && window.__iris.tone) || 'warm';
  const [messages, setMessages] = useStateChat(() => DAY_CONVOS[day] || DAY_CONVOS[47]);
  const [draft, setDraft] = useStateChat('');
  const [irisThinking, setIrisThinking] = useStateChat(false);
  const scrollRef = useRefChat(null);

  // Re-seed when day changes
  useEffectChat(() => {
    setMessages(DAY_CONVOS[day] || DAY_CONVOS[47]);
  }, [day]);

  // Autoscroll
  useEffectChat(() => {
    if (scrollRef.current) {
      const el = scrollRef.current;
      requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
    }
  }, [messages, irisThinking]);

  const send = (text) => {
    if (!text || !text.trim()) return;
    const next = [...messages, { who: 'me', text: text.trim() }];
    setMessages(next);
    setDraft('');
    setIrisThinking(true);
    setTimeout(() => {
      setIrisThinking(false);
      setMessages(prev => [...prev, { who: 'iris', text: generateIrisReply(text, day, tone) }]);
    }, 1100);
  };

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send(draft);
    }
  };

  const headers = DAY_HEADERS[day] || DAY_HEADERS[47];
  const inferred = DAY_INFERRED[day] || DAY_INFERRED[47];

  // Quick replies = those attached to the last Iris message
  const lastIris = [...messages].reverse().find(m => m.who === 'iris');
  const quickReplies = (lastIris && lastIris.quick) || [];

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      <div className="col" style={{ flex: 1, minWidth: 0 }}>
        <div className="row" style={{ alignItems: 'center', justifyContent: 'space-between', padding: '20px 40px 14px', borderBottom: '1px solid var(--line-soft)' }}>
          <div className="row" style={{ gap: 12, alignItems: 'center' }}>
            <span className="dot sage" style={{ animation: 'breathe 3s ease-in-out infinite' }} />
            <span className="kicker">Iris · {day === 1 ? 'meeting you' : day === 7 ? 'still learning' : 'listening'}</span>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <span className="tag">Tue, May 27 — eve</span>
            <span className="tag"><span className="dot sage" /> private</span>
            <span className="tag">day {day}</span>
          </div>
        </div>

        <div ref={scrollRef} style={{ flex: 1, overflow: 'auto', padding: '40px 60px 24px' }}>
          <div className="col" style={{ maxWidth: 720, margin: '0 auto' }}>
            <div className="kicker" style={{ marginBottom: 14 }}>{headers.eyebrow}</div>
            <div className="serif" style={{ fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em', marginBottom: 38 }}>
              {headers.title1}<br />
              <span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>{headers.title2}</span>
            </div>

            {messages.map((m, i) => <ChatMessage key={i} msg={m} />)}

            {irisThinking && (
              <div className="row" style={{ gap: 14, alignItems: 'flex-start', maxWidth: 640, marginBottom: 22 }}>
                <div className="iris-orb sm" style={{ marginTop: 6 }} />
                <div className="row" style={{ gap: 4, alignItems: 'center', height: 30 }}>
                  <span style={{ width: 4, height: 4, borderRadius: 999, background: 'var(--sage)', animation: 'blink 1.2s ease-in-out infinite' }} />
                  <span style={{ width: 4, height: 4, borderRadius: 999, background: 'var(--sage)', animation: 'blink 1.2s ease-in-out 0.2s infinite' }} />
                  <span style={{ width: 4, height: 4, borderRadius: 999, background: 'var(--sage)', animation: 'blink 1.2s ease-in-out 0.4s infinite' }} />
                </div>
              </div>
            )}
          </div>
        </div>

        <div style={{ padding: '14px 60px 28px', borderTop: '1px solid var(--line-soft)', background: 'var(--bg-0)' }}>
          <div style={{ maxWidth: 720, margin: '0 auto' }}>
            {quickReplies.length > 0 && (
              <div className="row" style={{ gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
                {quickReplies.map((q, i) => (
                  <button key={i} className="btn"
                    onClick={() => send(q)}
                    style={{ borderColor: 'var(--sage-dim)', color: 'var(--sage)' }}>{q}</button>
                ))}
              </div>
            )}
            <div style={{
              background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 10,
              padding: '14px 16px', display: 'flex', alignItems: 'flex-end', gap: 12,
            }}>
              <textarea
                value={draft}
                onChange={e => setDraft(e.target.value)}
                onKeyDown={onKey}
                placeholder="Talk to Iris… (⏎ to send, ⇧⏎ for new line)"
                rows={1}
                style={{
                  flex: 1, background: 'transparent', border: 'none', resize: 'none',
                  color: 'var(--ink)', fontFamily: 'var(--sans)', fontSize: 14,
                  lineHeight: 1.5, outline: 'none', minHeight: 22,
                }}
              />
              <div className="row" style={{ alignItems: 'center', gap: 8 }}>
                <button className="btn ghost" style={{ color: 'var(--ink-3)', fontSize: 14 }}>🎙</button>
                <button className="btn primary" style={{ padding: '7px 14px' }} onClick={() => send(draft)}>Send</button>
              </div>
            </div>
            <div className="row" style={{ justifyContent: 'space-between', marginTop: 10, fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--ink-4)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
              <span>End-to-end private · processed on device</span>
              <span>{messages.filter(m => m.who === 'me').length} messages · {day === 1 ? 'just met' : day === 7 ? '4 patterns forming' : '4 patterns surfaced'}</span>
            </div>
          </div>
        </div>
      </div>

      <InferredRail inferred={inferred} day={day} />
    </div>
  );
}

window.ChatScreen = ChatScreen;

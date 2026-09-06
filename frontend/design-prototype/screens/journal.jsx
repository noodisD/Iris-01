// screens/journal.jsx — Journal composer + recent entries

const JOURNAL_RECENT = [
  {
    date: 'Mon, May 26',
    title: 'The standup that ate lunch.',
    body: "The room felt fast. Joel pivoted twice. I noticed I was bracing my jaw the whole hour — only caught it when it ached at 3.",
    tags: ['work', 'body', 'anxiety'],
    irisNote: "this is the 3rd time you've mentioned jaw tension in a meeting.",
  },
  {
    date: 'Sun, May 25',
    title: 'A slow morning, finally.',
    body: "Coffee on the porch. Read 14 pages without checking my phone. Felt like the kind of slow I used to know.",
    tags: ['rest', 'reading'],
    irisNote: "longest unbroken read window in 22 days.",
  },
  {
    date: 'Sat, May 24',
    title: 'Big walk with M.',
    body: "We talked about August and didn't decide anything. That was kind of the point. Foggy at the trailhead, sunny by the top.",
    tags: ['relationships', 'movement'],
    irisNote: null,
  },
  {
    date: 'Fri, May 23',
    title: 'Couldn\'t fall asleep.',
    body: "Mind on the design review. Tried the breathing thing twice. The second time it actually worked, around 1.",
    tags: ['sleep', 'anxiety', 'work'],
    irisNote: "design review surfaced 9 days running.",
  },
];

const PHRASES_FOUND = [
  { phrase: 'bracing my jaw',           count: 3 },
  { phrase: 'mind on the design review', count: 9 },
  { phrase: 'slow morning',              count: 4 },
  { phrase: 'didn\'t decide anything',   count: 2 },
  { phrase: 'the kind of slow',          count: 2 },
];

function JournalScreen() {
  const [lines, setLines] = React.useState(['', '', '']);
  const [mood, setMood] = React.useState(6);

  return (
    <div className="row" style={{ height: '100%' }}>
      {/* Composer */}
      <div className="col" style={{ flex: 1, padding: '32px 56px 40px', minWidth: 0, overflow: 'auto' }}>
        <div className="row" style={{ alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 28 }}>
          <div className="col" style={{ gap: 6 }}>
            <div className="kicker">tuesday, may 27 · evening</div>
            <h1 className="serif" style={{ margin: 0, fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
              Three lines,<br /><span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>please.</span>
            </h1>
          </div>
          <div className="col gap-8" style={{ alignItems: 'flex-end' }}>
            <span className="kicker">how is today?</span>
            <div className="row" style={{ gap: 4 }}>
              {[1,2,3,4,5,6,7,8,9,10].map(n => (
                <button key={n} onClick={() => setMood(n)} style={{
                  width: 22, height: 22, borderRadius: '50%',
                  border: '1px solid ' + (n === mood ? 'var(--sage)' : 'var(--line)'),
                  background: n === mood ? 'var(--sage)' : 'transparent',
                  color: n === mood ? '#14140f' : 'var(--ink-3)',
                  fontFamily: 'var(--mono)', fontSize: 10, cursor: 'pointer', padding: 0,
                }}>{n}</button>
              ))}
            </div>
          </div>
        </div>

        {/* Three-lines composer */}
        <div className="col" style={{ gap: 8, maxWidth: 720 }}>
          {[
            'What happened today?',
            'What were you feeling?',
            'What do you want Iris to remember?',
          ].map((prompt, i) => (
            <div key={i} className="col" style={{ gap: 4, padding: '14px 0', borderBottom: '1px solid var(--line)' }}>
              <div className="row" style={{ alignItems: 'baseline', gap: 12 }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.1em', textTransform: 'uppercase', minWidth: 16 }}>0{i+1}</span>
                <span className="serif ital" style={{ fontSize: 18, color: 'var(--ink-3)' }}>{prompt}</span>
              </div>
              <textarea
                value={lines[i]}
                onChange={e => { const c = [...lines]; c[i] = e.target.value; setLines(c); }}
                placeholder={i === 0 ? "Standup ran long. Skipped lunch. Shipped the design review at 4 — felt the relief in my shoulders." : ''}
                rows={2}
                style={{
                  background: 'transparent', border: 'none', resize: 'none', outline: 'none',
                  color: 'var(--ink)', fontFamily: 'var(--serif)', fontSize: 20, lineHeight: 1.5,
                  padding: '4px 0 4px 28px', letterSpacing: '-0.005em',
                }}
              />
            </div>
          ))}
        </div>

        {/* Iris's reading of it */}
        <div style={{ marginTop: 28, padding: '18px 22px', background: 'var(--bg-2)', border: '1px solid var(--line-soft)', borderRadius: 10, maxWidth: 720 }}>
          <div className="row" style={{ gap: 12, alignItems: 'flex-start' }}>
            <div className="iris-orb sm" style={{ marginTop: 6 }} />
            <div className="col" style={{ flex: 1, gap: 8 }}>
              <div className="kicker">iris, reading along</div>
              <div className="serif ital" style={{ fontSize: 18, lineHeight: 1.35, color: 'var(--ink)' }}>
                "'Felt the relief in my shoulders' — I'll add that to your body-language vocabulary. You've used a shoulder-word for relief 4 times now."
              </div>
              <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                <span className="tag" style={{ color: 'var(--sage)', borderColor: 'var(--sage-dim)' }}>+ shoulders = relief</span>
                <span className="tag">+ skipped lunch</span>
                <span className="tag">+ win: design review</span>
                <span className="tag">+ tuesday standup</span>
              </div>
            </div>
          </div>
        </div>

        <div className="row" style={{ gap: 8, marginTop: 18, maxWidth: 720, justifyContent: 'flex-end' }}>
          <button className="btn">Save draft</button>
          <button className="btn">Save without Iris</button>
          <button className="btn primary">Save · 19s read</button>
        </div>
      </div>

      {/* Right rail — recent entries timeline */}
      <aside style={{ width: 380, flexShrink: 0, borderLeft: '1px dashed var(--line)', padding: '32px 28px', overflow: 'auto' }}>
        <div className="kicker" style={{ marginBottom: 8 }}>recent entries</div>
        <h3 className="serif" style={{ margin: '0 0 22px', fontSize: 24, lineHeight: 1 }}>4 of 47</h3>

        <div className="col" style={{ gap: 22 }}>
          {JOURNAL_RECENT.map((e, i) => (
            <article key={i} className="col" style={{ gap: 6 }}>
              <div className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between' }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{e.date}</span>
                <div className="row" style={{ gap: 4 }}>
                  {e.tags.map(t => <span key={t} style={{ fontSize: 9, fontFamily: 'var(--mono)', color: 'var(--ink-4)' }}>·{t}</span>)}
                </div>
              </div>
              <div className="serif" style={{ fontSize: 18, lineHeight: 1.2, color: 'var(--ink)' }}>{e.title}</div>
              <div style={{ fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.55 }}>{e.body}</div>
              {e.irisNote && (
                <div className="row" style={{ gap: 6, alignItems: 'flex-start', marginTop: 4, paddingLeft: 10, borderLeft: '1px solid var(--sage-dim)' }}>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--sage)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>iris:</span>
                  <span style={{ fontSize: 11, color: 'var(--ink-2)', fontStyle: 'italic' }}>{e.irisNote}</span>
                </div>
              )}
            </article>
          ))}
        </div>

        <hr className="dotline" style={{ margin: '28px 0 18px' }} />

        <div className="kicker" style={{ marginBottom: 10 }}>phrases iris keeps hearing</div>
        <div className="col" style={{ gap: 6 }}>
          {PHRASES_FOUND.map((p, i) => (
            <div key={i} className="row" style={{ alignItems: 'baseline', gap: 10 }}>
              <span style={{ flex: 1, fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: 14, color: 'var(--ink)' }}>"{p.phrase}"</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)' }}>×{p.count}</span>
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}

window.JournalScreen = JournalScreen;

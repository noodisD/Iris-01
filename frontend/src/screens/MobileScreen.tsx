import React from 'react';

/**
 * On-the-go / mobile companion preview.
 * This is a marketing/preview screen — static by design. The real mobile
 * app is a separate React Native / native target. Port the three phone
 * mockups from prototype screens/mobile.jsx if a richer preview is needed.
 */
export function MobileScreen() {
  return (
    <div className="col" style={{ padding: '24px 56px 48px', gap: 24, minHeight: '100%' }}>
      <header className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid var(--line)', paddingBottom: 18 }}>
        <div className="col" style={{ gap: 6 }}>
          <div className="kicker">on the go · iris on your phone</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
            Three moments,<br /><span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>one companion.</span>
          </h1>
        </div>
      </header>
      <p style={{ margin: 0, fontSize: 15, lineHeight: 1.55, color: 'var(--ink-2)', maxWidth: 720, fontFamily: 'var(--serif)' }}>
        The phone app is where Iris lives between desktop sessions — a soft prompt at the right hour, a glance at the body, a few lines when you have a minute. Same memory, fewer charts.
      </p>
      <div style={{ padding: '40px', border: '1px dashed var(--line)', borderRadius: 12, textAlign: 'center', color: 'var(--ink-3)' }}>
        <div className="iris-orb" style={{ margin: '0 auto 16px' }} />
        <div className="serif ital" style={{ fontSize: 20, color: 'var(--ink-2)' }}>
          The mobile preview (three phone mockups) ships as a separate React Native target.
        </div>
        <p style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.06em', textTransform: 'uppercase', marginTop: 14 }}>
          PARTIAL PORT · phone bezels in prototype screens/mobile.jsx
        </p>
      </div>
    </div>
  );
}

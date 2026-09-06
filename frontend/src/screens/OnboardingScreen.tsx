import React from 'react';
import { useNavigate } from 'react-router-dom';

/**
 * Onboarding — conversational first-run.
 * PARTIAL: the prototype (screens/onboarding.jsx) implements the full
 * branching chat (name → reason → threads → pair-body → review). Wire that
 * state machine to src/api/onboarding.ts here. This stub links into the app.
 */
export function OnboardingScreen() {
  const nav = useNavigate();
  return (
    <div className="col" style={{ alignItems: 'center', justifyContent: 'center', minHeight: '100%', gap: 24, padding: 56, textAlign: 'center' }}>
      <div className="iris-orb lg" />
      <h1 className="serif" style={{ margin: 0, fontSize: 56, lineHeight: 1, letterSpacing: '-0.02em' }}>
        Hi. I'm <span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>Iris</span>.
      </h1>
      <p style={{ maxWidth: 460, fontSize: 16, color: 'var(--ink-2)', lineHeight: 1.55, fontFamily: 'var(--serif)' }}>
        Before we start, three things: I live on this device, I'm slow at first, and everything I remember is editable. Ready when you are.
      </p>
      <button className="btn primary" onClick={() => nav('/chat')}>Yes — let's start →</button>
      <p style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
        PARTIAL PORT · full branching flow in prototype screens/onboarding.jsx · wire to api/onboarding.ts
      </p>
    </div>
  );
}

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { completeOnboarding } from '@/api/onboarding';
import { qk } from '@/lib/queryClient';

/**
 * First run. Deliberately short: it records that onboarding happened so the
 * app stops redirecting here, and gets out of the way.
 */
export function OnboardingScreen() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [busy, setBusy] = React.useState(false);

  const start = async () => {
    setBusy(true);
    try {
      await completeOnboarding();
      await qc.invalidateQueries({ queryKey: qk.onboarding });
      nav('/chat');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="col" style={{ alignItems: 'center', justifyContent: 'center', minHeight: '100%', gap: 24, padding: 56, textAlign: 'center' }}>
      <div className="iris-orb lg" />
      <h1 className="serif" style={{ margin: 0, fontSize: 56, lineHeight: 1, letterSpacing: '-0.02em' }}>
        Hi. I'm <span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>Iris</span>.
      </h1>
      <p style={{ maxWidth: 460, fontSize: 16, color: 'var(--ink-2)', lineHeight: 1.55, fontFamily: 'var(--serif)' }}>
        Three things before we start. I run on this machine and everything I store stays in
        your own database — though what you write is sent to OpenAI to be turned into
        embeddings and replies. I need about a week of entries before I notice anything worth
        saying. And everything I come to believe about you is visible, and removable, in
        Settings.
      </p>
      <button className="btn primary" onClick={start} disabled={busy}>
        {busy ? 'One moment…' : "Yes — let's start →"}
      </button>
    </div>
  );
}

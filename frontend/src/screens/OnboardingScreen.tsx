import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { completeOnboarding } from '@/api/onboarding';
import { qk } from '@/lib/queryClient';
import { Button, Lens } from '@/ui';
import styles from './OnboardingScreen.module.css';

/**
 * First run. Deliberately short: it records that onboarding happened so the
 * app stops redirecting here, and gets out of the way.
 */
export function OnboardingScreen() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      await completeOnboarding();
      await qc.invalidateQueries({ queryKey: qk.onboarding });
      nav('/chat');
    } catch (err) {
      // The button used to just unstick, leaving the owner here with no idea
      // why pressing it did nothing.
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.page}>
      <Lens size={72} />
      <h1 className={styles.title}>Hi, I&apos;m Iris.</h1>
      <div className={styles.body}>
        <p>Three things before we start.</p>
        <ul>
          <li>I run on this machine, and everything I store stays in your own database. What you write is sent to
            OpenAI to be turned into embeddings and replies.</li>
          <li>I need about a week of entries before I notice anything worth saying.</li>
          <li>Everything I come to believe about you is visible, and removable, in Settings.</li>
        </ul>
      </div>
      <Button variant="primary" onClick={start} disabled={busy}>{busy ? 'One moment…' : 'Start'}</Button>
      {error && <p role="alert" className={styles.error}>Couldn&apos;t start: {error}</p>}
    </div>
  );
}

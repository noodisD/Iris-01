import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { getVoiceEstimate } from '@/api/voice';
import type { useTalk } from '@/hooks/useTalk';
import type { TalkPhase } from '@/lib/talk';
import { Button, Lens } from '@/ui';
import styles from './TalkMode.module.css';

type Talk = ReturnType<typeof useTalk>;

const SAYS: Record<TalkPhase, string> = {
  off: '',
  starting: 'Getting the microphone ready',
  listening: 'Listening',
  hearing: 'Listening',
  thinking: 'Thinking',
  speaking: 'IRIS is speaking',
  paused: 'Paused',
  error: 'Talking stopped',
};

/**
 * Before anything is sent: what talking sends where, and what a turn costs
 * (ADR-0025). Nothing leaves until Start talking.
 */
export function TalkIntro({ onStart, onCancel }: { onStart: () => void; onCancel: () => void }) {
  const estimate = useQuery({ queryKey: ['voice', 'estimate'], queryFn: getVoiceEstimate, staleTime: 60_000 });
  return (
    <section className={styles.intro} role="dialog" aria-label="Talk with IRIS">
      <h2 className={styles.introTitle}>Talk with IRIS</h2>
      <p>
        IRIS listens until you stop, then answers aloud. What you say is sent to OpenAI to be written down, your
        words and IRIS&apos;s usual context go to the model to reply, and the reply is sent back to be spoken. Only
        the words are kept, as chat messages; the audio is not.
      </p>
      <p className={styles.cost}>
        {estimate.isPending ? 'Working out the cost…'
          : estimate.isError ? 'The cost could not be worked out.'
          : `${estimate.data.perTurn}, on ${estimate.data.model}.`}
      </p>
      <div className={styles.actions}>
        <Button variant="primary" onClick={onStart}>Start talking</Button>
        <Button variant="quiet" onClick={onCancel}>Cancel</Button>
      </div>
    </section>
  );
}

/** The conversation itself: the lens, what IRIS is doing, and three controls. */
export function TalkMode({ talk }: { talk: Talk }) {
  const { state } = talk;
  const { phase } = state;

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const typing = event.target instanceof HTMLElement
        && ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(event.target.tagName);
      if (event.key === 'Escape' && phase === 'speaking') { event.preventDefault(); talk.stopSpeaking(); }
      if (event.key === ' ' && !typing) {
        event.preventDefault();
        if (phase === 'paused') talk.resume();
        else if (phase === 'listening' || phase === 'hearing' || phase === 'speaking') talk.pause();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [phase, talk]);

  const live = phase === 'hearing' || phase === 'speaking';
  return (
    <section className={styles.talk} aria-label="Talking with IRIS" data-phase={phase} ref={talk.levelRef}>
      <div className={styles.lens}><Lens size={112} live={live} /></div>
      <p className={styles.state} aria-live="polite">{SAYS[phase]}</p>
      {state.error && <p role="alert" className={styles.error}>{state.error}</p>}
      <div className={styles.actions}>
        {phase === 'error' ? (
          <Button variant="primary" onClick={() => void talk.start()}>Try again</Button>
        ) : phase === 'paused' ? (
          <Button onClick={talk.resume}>Resume listening</Button>
        ) : (
          <Button onClick={talk.pause} disabled={phase === 'starting' || phase === 'thinking'}>Pause listening</Button>
        )}
        {phase === 'speaking' && <Button onClick={talk.stopSpeaking}>Stop speaking</Button>}
        <Button variant="quiet" onClick={talk.end}>End</Button>
      </div>
      <p className={styles.hint}>Talk over IRIS to interrupt. Space pauses listening, Esc stops IRIS speaking.</p>
    </section>
  );
}

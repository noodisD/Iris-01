import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation } from 'react-router-dom';
import { getHealthLatest } from '@/api/health';
import { Button } from '@/ui';
import styles from './HealthBanner.module.css';

const HIDDEN_KEY = 'iris.health.hidden';

function hiddenRun(): string | null {
  try { return localStorage.getItem(HIDDEN_KEY); } catch { return null; }
}

/**
 * What the doctor's last daily run found: problems first, then what waits on
 * the owner. Hidden until the next run when dismissed; quiet when all is well.
 */
export function HealthBanner() {
  const { data } = useQuery({ queryKey: ['health', 'latest'], queryFn: getHealthLatest,
    refetchInterval: 15 * 60 * 1000, retry: false });
  const [open, setOpen] = React.useState(false);
  const [hidden, setHidden] = React.useState(hiddenRun);
  // Chat fills the window exactly; a bar above it would push the composer off screen.
  const onChat = useLocation().pathname.startsWith('/chat');
  if (onChat || !data?.runId || data.attention.length === 0 || hidden === data.runId) return null;

  const problems = data.attention.filter(a => a.status === 'fail' || a.status === 'warn' || a.status === 'unknown');
  const waiting = data.attention.filter(a => a.status === 'waiting');
  const failing = problems.some(a => a.status === 'fail');
  const tone = failing ? styles.fail : problems.length ? styles.warn : styles.waiting;
  const headline = [
    problems.length ? `${problems.length} health ${problems.length === 1 ? 'check needs' : 'checks need'} attention` : '',
    waiting.length ? `${waiting.length} ${waiting.length === 1 ? 'thing is' : 'things are'} waiting on you` : '',
  ].filter(Boolean).join(' · ');
  const when = data.runAt ? new Date(data.runAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '';

  return (
    <section className={`${styles.banner} ${tone}`} aria-label="IRIS health">
      <div className={styles.row}>
        <p className={styles.headline} role="status">{headline}</p>
        <span className={styles.when}>checked {when}</span>
        <Button size="sm" variant="quiet" aria-expanded={open} onClick={() => setOpen(o => !o)}>
          {open ? 'Hide details' : 'Details'}
        </Button>
        <Button size="sm" variant="quiet" onClick={() => {
          try { localStorage.setItem(HIDDEN_KEY, data.runId!); } catch { /* the banner just stays */ }
          setHidden(data.runId);
        }}>Hide until next check</Button>
      </div>
      {open && (
        <ul className={styles.list}>
          {[...problems, ...waiting].map(a => (
            <li key={a.id}><span className={styles.status}>{a.status === 'waiting' ? 'waiting' : a.status}</span>
              {a.summary}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

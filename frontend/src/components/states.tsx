import type React from 'react';
import { Button, Lens } from '@/ui';
import styles from './states.module.css';

/** Generic loading placeholder: a calm pulsing block. */
export function Skeleton({ h = 16, w = '100%', radius = 6 }: { h?: number; w?: number | string; radius?: number }) {
  return <div className={styles.skeleton} style={{ height: h, width: w, borderRadius: radius }} />;
}

/** Waiting for data, with the lens. */
export function LoadingState({ label = 'Iris is gathering your day…' }: { label?: string }) {
  return (
    <div className={styles.state} role="status">
      <Lens size={40} />
      <p className={styles.label}>{label}</p>
    </div>
  );
}

/** Something failed to load: say so plainly, and offer a retry. */
export function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div className={styles.state}>
      <h2 className={styles.title}>Something didn't load.</h2>
      <p className={styles.body}>
        {message ?? "Iris couldn't reach your data just now. Your information is safe; only the view failed."}
      </p>
      {onRetry && <Button onClick={onRetry}>Try again</Button>}
    </div>
  );
}

/** Nothing here yet: an invitation to act. */
export function EmptyState({ title, body, action }: { title: string; body?: string; action?: React.ReactNode }) {
  return (
    <div className={styles.state}>
      <h2 className={styles.title}>{title}</h2>
      {body && <p className={styles.body}>{body}</p>}
      {action}
    </div>
  );
}

import type React from 'react';
import styles from './Badge.module.css';

/** A short status word. `confirmed` is gold: something the owner confirmed. */
export function Badge({ children, tone = 'neutral' }: {
  children: React.ReactNode; tone?: 'neutral' | 'confirmed' | 'better' | 'worse' | 'action';
}) {
  return <span className={`${styles.badge} ${styles[tone]}`}>{children}</span>;
}

/** A number with its label. Numbers in tabular figures. */
export function Stat({ value, label }: { value: React.ReactNode; label: React.ReactNode }) {
  return (
    <div className={styles.stat}>
      <span className={styles.value}>{value}</span>
      <span className={styles.label}>{label}</span>
    </div>
  );
}

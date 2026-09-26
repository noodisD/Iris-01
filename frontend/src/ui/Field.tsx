import React from 'react';
import styles from './Field.module.css';

/** A labelled control with an optional hint and error. The label names the control. */
export function Field({ label, hint, error, children, inline }: {
  label: string; hint?: React.ReactNode; error?: React.ReactNode; inline?: boolean;
  children: React.ReactElement<{ id?: string; 'aria-describedby'?: string; 'aria-invalid'?: boolean }>;
}) {
  const id = React.useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const control = React.cloneElement(children, {
    id,
    'aria-describedby': [hintId, errorId].filter(Boolean).join(' ') || undefined,
    'aria-invalid': error ? true : undefined,
  });
  return (
    <div className={inline ? styles.inline : styles.field}>
      <label htmlFor={id} className={styles.label}>{label}</label>
      {control}
      {hint && <p id={hintId} className={styles.hint}>{hint}</p>}
      {error && <p id={errorId} role="alert" className={styles.error}>{error}</p>}
    </div>
  );
}

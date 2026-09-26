import React from 'react';
import styles from './Button.module.css';

type Variant = 'primary' | 'secondary' | 'quiet' | 'danger';

/** One button for the whole app. Its label says what happens: "Save entry", not "Submit". */
export const Button = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant; size?: 'sm' | 'md'; icon?: React.ReactNode;
}>(function Button({ variant = 'secondary', size = 'md', icon, className, children, type = 'button', ...rest }, ref) {
  return (
    <button ref={ref} type={type} className={[styles.button, styles[variant], styles[size], className].filter(Boolean).join(' ')} {...rest}>
      {icon}{children}
    </button>
  );
});

/** A button that is only an icon. `label` is required: it is the button's name. */
export const IconButton = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string; icon: React.ReactNode;
}>(function IconButton({ label, icon, className, type = 'button', ...rest }, ref) {
  return (
    <button ref={ref} type={type} aria-label={label} title={label}
      className={[styles.button, styles.quiet, styles.icon, className].filter(Boolean).join(' ')} {...rest}>
      {icon}
    </button>
  );
});

import * as ToggleGroup from '@radix-ui/react-toggle-group';
import styles from './ChoiceGroup.module.css';

export interface Choice<T extends string> { value: T; label: string }

/**
 * Pick one of a few: verdicts, filters, check-in scores. Keyboard: arrow keys
 * move, space picks. `clearable` lets picking the current answer again clear it.
 * `tone="confirm"` shows the pick in gold: a judgement the owner made.
 */
export function ChoiceGroup<T extends string>({ label, options, value, onChange, clearable, disabled, tone = 'select', shape = 'pill' }: {
  label: string;
  options: Choice<T>[];
  value: T | null | undefined;
  onChange: (value: T | null) => void;
  clearable?: boolean;
  disabled?: boolean;
  tone?: 'select' | 'confirm';
  shape?: 'pill' | 'round';
}) {
  return (
    <ToggleGroup.Root type="single" aria-label={label} className={styles.group} disabled={disabled}
      value={value ?? ''} onValueChange={next => {
        if (next) onChange(next as T);
        else if (clearable) onChange(null);
      }}>
      {options.map(option => (
        <ToggleGroup.Item key={option.value} value={option.value}
          className={[styles.item, styles[shape], tone === 'confirm' ? styles.confirm : styles.select].join(' ')}>
          {option.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}

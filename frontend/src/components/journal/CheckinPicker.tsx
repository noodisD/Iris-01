import styles from './CheckinPicker.module.css';

export const CHECKIN_ROWS = [
  { key: 'energy', label: 'energy', title: 'Energy' },
  { key: 'mood', label: 'mood', title: 'Mood' },
  { key: 'sleep_quality', label: 'sleep', title: 'Sleep' },
  { key: 'stress', label: 'stress', title: 'Stress' },
  { key: 'focus', label: 'focus', title: 'Focus' },
] as const;

export type CheckinKey = (typeof CHECKIN_ROWS)[number]['key'];
export type CheckinValues = Record<CheckinKey, number | null>;

export function emptyCheckin(): CheckinValues {
  return { energy: null, mood: null, sleep_quality: null, stress: null, focus: null };
}

/** Five optional scores, 1-10. Picking the chosen number again clears it. */
export function CheckinPicker({
  value,
  onChange,
}: {
  value: CheckinValues;
  onChange: (next: CheckinValues) => void;
}) {
  return (
    <fieldset className={styles.checkin}>
      <legend className={styles.legend}>Check-in <span>optional, 1 to 10</span></legend>
      {CHECKIN_ROWS.map(row => (
        <div key={row.key} className={styles.row} role="group" aria-label={row.title}>
          <span className={styles.label} aria-hidden>{row.title}</span>
          <div className={styles.scale}>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(n => (
              <button
                key={n}
                type="button"
                className={styles.chip}
                aria-label={`${row.label} ${n}`}
                aria-pressed={value[row.key] === n}
                onClick={() => onChange({ ...value, [row.key]: value[row.key] === n ? null : n })}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
      ))}
    </fieldset>
  );
}

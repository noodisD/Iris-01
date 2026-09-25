import type { CSSProperties } from 'react';

export const CHECKIN_ROWS = [
  { key: 'energy', label: 'energy' },
  { key: 'mood', label: 'mood' },
  { key: 'sleep_quality', label: 'sleep' },
  { key: 'stress', label: 'stress' },
  { key: 'focus', label: 'focus' },
] as const;

export type CheckinKey = (typeof CHECKIN_ROWS)[number]['key'];
export type CheckinValues = Record<CheckinKey, number | null>;

export function emptyCheckin(): CheckinValues {
  return { energy: null, mood: null, sleep_quality: null, stress: null, focus: null };
}

function chip(selected: boolean): CSSProperties {
  return {
    width: 22,
    height: 22,
    borderRadius: '50%',
    border: `1px solid ${selected ? 'var(--sage)' : 'var(--line)'}`,
    background: selected ? 'var(--sage)' : 'transparent',
    color: selected ? '#14140f' : 'var(--ink-3)',
    fontFamily: 'var(--mono)',
    fontSize: 10,
    cursor: 'pointer',
    padding: 0,
  };
}

export function CheckinPicker({
  value,
  onChange,
}: {
  value: CheckinValues;
  onChange: (next: CheckinValues) => void;
}) {
  return (
    <div className="col" style={{ gap: 6 }}>
      <span className="kicker">check-in · optional</span>
      {CHECKIN_ROWS.map(row => (
        <div key={row.key} className="row" style={{ gap: 8, alignItems: 'center' }}>
          <span style={{ width: 52, fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            {row.label}
          </span>
          <div className="row" style={{ gap: 3, alignItems: 'center' }}>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(n => (
              <button
                key={n}
                type="button"
                aria-label={`${row.label} ${n}`}
                aria-pressed={value[row.key] === n}
                onClick={() => onChange({ ...value, [row.key]: value[row.key] === n ? null : n })}
                style={chip(value[row.key] === n)}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

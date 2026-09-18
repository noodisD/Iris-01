/**
 * A calendar day is not an instant.
 *
 * `new Date('2026-05-10')` is parsed as UTC midnight, so anywhere west of
 * Greenwich it renders as the 9th. Every imported entry's date slipped a day
 * for a reader in Los Angeles, and the journal quietly disagreed with itself
 * about when things were written.
 *
 * A date-only value is a day the owner lived through. It has no time and no
 * zone, so it is read field by field and never turned into an instant. A value
 * that really is a timestamp keeps its normal handling.
 */

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

export const DAY_WITH_WEEKDAY: Intl.DateTimeFormatOptions = {
  weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
};

export const DAY_LONG: Intl.DateTimeFormatOptions = {
  day: 'numeric', month: 'long', year: 'numeric',
};

/** Turn a `YYYY-MM-DD` (or full timestamp) into text, without shifting the day. */
export function formatEventDate(
  value: string | null | undefined,
  opts: Intl.DateTimeFormatOptions = DAY_WITH_WEEKDAY,
): string {
  if (!value) return '';
  const parts = DATE_ONLY.exec(value);
  const d = parts
    ? new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]))
    : new Date(value);
  // An unparseable value is shown as it arrived rather than as "Invalid Date".
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(undefined, opts);
}

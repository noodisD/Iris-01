/**
 * Shared visual primitives — typed React versions of the prototype's charts.
 * Pure presentational: they take data, draw SVG. No data fetching here.
 */

export function Orb({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  return <div className={`iris-orb ${size === 'lg' ? 'lg' : size === 'sm' ? 'sm' : ''}`} />;
}

/** Color token resolver: maps 'sage'|'rose'|… to a CSS var, passes through hex. */
export function color(token: string): string {
  const map: Record<string, string> = {
    sage: 'var(--sage)', amber: 'var(--amber)', indigo: 'var(--indigo)', rose: 'var(--rose)',
    ink: 'var(--ink)', 'ink-2': 'var(--ink-2)', 'ink-3': 'var(--ink-3)',
  };
  return map[token] ?? token;
}

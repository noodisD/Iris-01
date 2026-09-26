/**
 * Shared visual primitives — typed React versions of the prototype's charts.
 * Pure presentational: they take data, draw SVG. No data fetching here.
 */

import { Lens } from '@/ui/Lens';

/** The iris lens at one of three sizes. */
export function Orb({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  return <Lens size={size === 'lg' ? 56 : size === 'sm' ? 16 : 26} />;
}

/** Colour resolver for stored colour names (a habit's colour): a categorical hue, or a hex passed through. */
export function color(token: string): string {
  const map: Record<string, string> = {
    sage: 'var(--hue-green)', amber: 'var(--hue-amber)', indigo: 'var(--hue-blue)', rose: 'var(--hue-rose)',
    ink: 'var(--petal)', 'ink-2': 'var(--petal-2)', 'ink-3': 'var(--petal-3)',
  };
  return map[token] ?? token;
}

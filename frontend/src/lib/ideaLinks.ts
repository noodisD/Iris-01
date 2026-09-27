import type { LinkKind } from '@/types/api';

/** How each relation between two ideas reads, as "<from> <label> <to>". */
export const LINK_LABEL: Record<LinkKind, string> = {
  same_meaning: 'means the same as',
  applies: 'is an application of',
  supports: 'supports',
  refines: 'refines',
  depends_on: 'depends on',
  contradicts: 'contradicts',
};

/** Relations with no direction: swapping the two ideas changes nothing. */
export const SYMMETRIC: ReadonlySet<LinkKind> = new Set<LinkKind>(['same_meaning', 'contradicts']);

/** In the order offered when the owner names a relation. */
export const LINK_KINDS = Object.keys(LINK_LABEL) as LinkKind[];

/** A line's colour on the map, per relation. */
export const LINK_COLOR: Record<LinkKind, string> = {
  same_meaning: '#e3c26b',
  applies: '#e39ad0',
  supports: '#8fc4a8',
  refines: '#9aa6e0',
  depends_on: '#d9a877',
  contradicts: '#d98a8a',
};

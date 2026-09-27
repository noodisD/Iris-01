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

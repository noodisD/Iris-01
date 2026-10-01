import type { EvidenceRef } from '@/types/api';

const sha256 = /^[0-9a-f]{64}$/;
const periods = new Set(['all', '30d', '90d']);
const outcomes = new Set(['energy', 'mood', 'sleep_quality', 'stress', 'focus']);
const splits = new Set(['office_home', 'commute', 'steps', 'screen_time', 'social_share', 'sleep']);

/** The server revalidates ownership and freshness. This only rejects malformed navigation. */
export function parseEvidenceRef(raw: string | null): EvidenceRef | null {
  if (!raw || raw.length > 2048) return null;
  let value: unknown;
  try { value = JSON.parse(raw); } catch { return null; }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const item = value as Record<string, unknown>;
  if (!periods.has(item.range as string) || typeof item.snapshot !== 'string' || !sha256.test(item.snapshot)) return null;
  const expected = item.kind === 'dynamic' ? ['kind', 'dynamicId', 'range', 'snapshot']
    : item.kind === 'personal_insight' ? ['kind', 'insightId', 'range', 'snapshot']
    : item.kind === 'day' ? ['kind', 'outcome', 'split', 'range', 'snapshot'] : [];
  if (expected.length === 0 || Object.keys(item).length !== expected.length
    || expected.some(key => !(key in item))) return null;
  if (item.kind === 'day') {
    return outcomes.has(item.outcome as string) && splits.has(item.split as string) ? item as EvidenceRef : null;
  }
  const id = item.kind === 'dynamic' ? item.dynamicId : item.insightId;
  return typeof id === 'string' && /^(d_|i_)[0-9a-f]{64}$/.test(id)
    && (item.kind === 'dynamic' ? id.startsWith('d_') : id.startsWith('i_'))
    ? item as EvidenceRef : null;
}

export function evidenceHref(ref: EvidenceRef): string {
  return `/chat?evidence=${encodeURIComponent(JSON.stringify(ref))}`;
}

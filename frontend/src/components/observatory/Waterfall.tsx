import type { ObsSpanSummary } from '@/api/observatory';
import { ms } from '@/lib/obsFormat';

interface Row { span: ObsSpanSummary; depth: number; left: number; width: number; skew: boolean }

function tree(spans: ObsSpanSummary[]): Row[] {
  const byParent = new Map<string, ObsSpanSummary[]>();
  const ids = new Set(spans.map(span => span.span_id));
  for (const span of spans) {
    const parent = span.parent_span_id && ids.has(span.parent_span_id) ? span.parent_span_id : '';
    const list = byParent.get(parent) ?? [];
    list.push(span);
    byParent.set(parent, list);
  }
  for (const list of byParent.values()) list.sort((a, b) => a.started_at.localeCompare(b.started_at));
  const rows: { span: ObsSpanSummary; depth: number }[] = [];
  const walk = (parent: string, depth: number) => {
    for (const span of byParent.get(parent) ?? []) {
      rows.push({ span, depth });
      walk(span.span_id, depth + 1);
    }
  };
  walk('', 0);
  if (rows.length === 0) return [];
  const start = (span: ObsSpanSummary) => Date.parse(span.started_at);
  const end = (span: ObsSpanSummary) => start(span) + span.duration_ms;
  let t0 = Math.min(...rows.map(row => start(row.span)));
  let t1 = Math.max(...rows.map(row => end(row.span)));
  const widened = new Map<string, { start: number; end: number; skew: boolean }>();
  for (const row of rows) {
    if (row.span.component !== 'web' && row.span.component !== 'android') continue;
    const children = spans.filter(span => span.parent_span_id === row.span.span_id);
    if (children.length === 0) continue;
    const childStart = Math.min(...children.map(start));
    const childEnd = Math.max(...children.map(end));
    const ownStart = start(row.span);
    const ownEnd = end(row.span);
    const skew = ownStart - childStart > 50 || childEnd - ownEnd > 50;
    widened.set(row.span.span_id, {
      start: Math.min(ownStart, childStart),
      end: Math.max(ownEnd, childEnd),
      skew,
    });
  }
  for (const box of widened.values()) {
    t0 = Math.min(t0, box.start);
    t1 = Math.max(t1, box.end);
  }
  const spanMs = Math.max(1, t1 - t0);
  return rows.slice(0, 2000).map(row => {
    const box = widened.get(row.span.span_id);
    const began = box?.start ?? start(row.span);
    const duration = (box?.end ?? end(row.span)) - began;
    return {
      span: row.span,
      depth: row.depth,
      left: ((began - t0) / spanMs) * 100,
      width: Math.max(0.3, (duration / spanMs) * 100),
      skew: box?.skew ?? false,
    };
  });
}

export function Waterfall({ spans, selected, onSelect }: {
  spans: ObsSpanSummary[];
  selected: string | null;
  onSelect: (spanId: string) => void;
}) {
  const rows = tree(spans);
  return (
    <div>
      {rows.map(row => (
        <button
          key={row.span.span_id}
          type="button"
          data-depth={row.depth}
          onClick={() => onSelect(row.span.span_id)}
          style={{
            display: 'grid',
            gridTemplateColumns: '240px 1fr',
            gap: 8,
            width: '100%',
            textAlign: 'left',
            paddingLeft: 8 + row.depth * 16,
            background: selected === row.span.span_id ? 'var(--dusk-2)' : 'transparent',
            border: 0,
            color: 'inherit',
          }}
        >
          <span>{row.span.name} · {ms(row.span.duration_ms)}{row.skew ? ' · Clock skew adjusted' : ''}</span>
          <span style={{ position: 'relative', height: 16 }}>
            <span style={{
              position: 'absolute', left: `${row.left}%`, width: `${row.width}%`, height: 10, top: 3,
              background: row.span.status === 'error' ? 'var(--worse)' : 'var(--iris)',
              borderRadius: 3,
            }} />
          </span>
        </button>
      ))}
      {spans.length > 2000 && <p>Showing 2,000 of {spans.length} spans</p>}
    </div>
  );
}

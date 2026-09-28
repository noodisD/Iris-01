import { useNavigate } from 'react-router-dom';
import type { ObsComponentStatus, ObsEdge } from '@/api/observatory';
import { ms } from '@/lib/obsFormat';

const CENTRES: Record<string, [number, number]> = {
  web: [90, 190], android: [90, 330], http: [290, 260],
  chat: [500, 50], voice: [500, 120], import: [500, 190], sensors: [500, 260], ideas: [500, 330], insights: [500, 400],
  queue: [720, 120], pipeline: [720, 200], admission: [720, 330], engine: [720, 410],
  llm: [920, 120], db: [920, 260], system: [920, 400],
};

const STROKE: Record<string, string> = {
  failing: 'var(--worse)', degraded: 'var(--caution)', ok: 'var(--better)', idle: 'var(--mist)',
};

function line(source: string, target: string): string {
  const [x1, y1] = CENTRES[source] ?? [0, 0];
  const [x2, y2] = CENTRES[target] ?? [0, 0];
  if (x2 > x1) return `M ${x1 + 80} ${y1} C ${x1 + 120} ${y1}, ${x2 - 120} ${y2}, ${x2 - 80} ${y2}`;
  if (x2 < x1) return `M ${x1 - 80} ${y1} C ${x1 - 120} ${y1}, ${x2 + 120} ${y2}, ${x2 + 80} ${y2}`;
  const bulge = x1 + 40;
  return y2 > y1
    ? `M ${x1} ${y1 + 24} C ${bulge} ${y1 + 24}, ${bulge} ${y2 - 24}, ${x2} ${y2 - 24}`
    : `M ${x1} ${y1 - 24} C ${bulge} ${y1 - 24}, ${bulge} ${y2 + 24}, ${x2} ${y2 + 24}`;
}

export function SystemMap({ components, edges }: { components: ObsComponentStatus[]; edges: ObsEdge[] }) {
  const navigate = useNavigate();
  const byId = new Map(components.map(item => [item.id, item]));
  return (
    <div style={{ overflowX: 'auto' }}>
      <svg viewBox="0 0 1000 470" style={{ minWidth: 640, width: '100%' }} role="img" aria-label="System map">
        <defs>
          <marker id="obs-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6" fill="var(--mist-2)" />
          </marker>
        </defs>
        {edges.map(edge => {
          const width = Math.min(6, 1 + 2 * Math.log10((edge.calls || 0) + 1));
          const bad = edge.calls > 0 && edge.errors / edge.calls >= 0.05;
          return (
            <path key={`${edge.source}-${edge.target}`} d={line(edge.source, edge.target)} fill="none"
              stroke={bad ? 'var(--worse)' : 'var(--mist-2)'} strokeWidth={width} markerEnd="url(#obs-arrow)" />
          );
        })}
        {Object.entries(CENTRES).map(([id, [x, y]]) => {
          const item = byId.get(id);
          const state = item?.state ?? 'idle';
          const second = id === 'system'
            ? `${Math.round(Number((item as unknown as { rss?: number })?.rss ?? 0))} MB, lag ${ms(null)}`
            : item && item.calls > 0
              ? `${item.rate_per_min.toFixed(1)}/min, p95 ${ms(item.p95_ms)}`
              : 'idle';
          const systemLine = id === 'system' && item
            ? systemCaption(item)
            : second;
          return (
            <g key={id} role="button" tabIndex={0} aria-label={`${item?.label ?? id}: ${state}`}
              onClick={() => navigate(`?view=system&component=${id}`)}
              onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); navigate(`?view=system&component=${id}`); } }}>
              <rect x={x - 80} y={y - 24} width="160" height="48" rx="8" fill="var(--dusk)" stroke={STROKE[state] ?? 'var(--mist)'} />
              <text x={x} y={y - 4} textAnchor="middle" fill="var(--petal)" fontSize="13">{item?.label ?? id}</text>
              <text x={x} y={y + 14} textAnchor="middle" fill="var(--petal-3)" fontSize="11">{systemLine}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function systemCaption(item: ObsComponentStatus): string {
  const probe = item as ObsComponentStatus & { probe?: { process?: { rss_bytes?: number }; loop?: { lag_ms_max?: number } } };
  const rss = probe.probe?.process?.rss_bytes;
  const lag = probe.probe?.loop?.lag_ms_max;
  if (rss == null && lag == null) return 'idle';
  return `${Math.round((rss ?? 0) / (1024 * 1024))} MB, lag ${Math.round(lag ?? 0)} ms`;
}

import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useInsights, useInsight } from '@/hooks/useInsights';
import { LoadingState, ErrorState, EmptyState } from '@/components/states';
import { color } from '@/components/primitives';
import type { InsightSummary, InsightEvidence } from '@/types/api';

// ─── Index ────────────────────────────────────────────────────────────────

function Card({ insight, onOpen }: { insight: InsightSummary; onOpen: (id: string) => void }) {
  const c = color(insight.accentColor);
  return (
    <article onClick={() => onOpen(insight.id)} style={{
      cursor: 'pointer', padding: '24px 28px',
      background: insight.featured ? 'rgba(169,200,163,0.04)' : 'var(--bg-2)',
      border: `1px solid ${insight.featured ? 'var(--sage-dim)' : 'var(--line-soft)'}`,
      borderRadius: 12, display: 'flex', flexDirection: 'column', gap: 12, minHeight: 280,
      gridColumn: insight.featured ? 'span 2' : 'span 1',
    }}>
      <div className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div className="row" style={{ gap: 8, alignItems: 'baseline' }}>
          <span className="kicker" style={{ color: c }}>{insight.kind}</span>
          {insight.featured && <span className="tag" style={{ color: 'var(--sage)', borderColor: 'var(--sage-dim)' }}>★ featured</span>}
        </div>
        {!insight.seen && <span className="dot sage" />}
      </div>
      <h3 className="serif" style={{ margin: 0, fontSize: insight.featured ? 48 : 30, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
        {insight.headline.line1}<br />
        <span style={{ color: c }}>{insight.headline.line2}</span><br />
        <span style={{ fontStyle: 'italic', color: 'var(--ink-2)' }}>{insight.headline.line3}</span>
      </h3>
      <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: 'var(--ink-3)', maxWidth: 520 }}>{insight.summary}</p>
      <div style={{ flex: 1 }} />
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
          {insight.tags.map((t, i) => <span key={i} className="tag">{t}</span>)}
        </div>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: c }}>open ↗</span>
      </div>
    </article>
  );
}

function IndexView() {
  const { data, isLoading, isError, refetch } = useInsights();
  const nav = useNavigate();
  if (isLoading) return <LoadingState label="Iris is reviewing your patterns…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;
  if (data.length === 0) return <EmptyState title="No patterns yet." body="Iris needs about a week of conversations and entries before she'll surface anything. She won't guess." />;

  const newCount = data.filter(i => !i.seen).length;

  return (
    <div className="col" style={{ padding: '32px 56px 48px', gap: 28 }}>
      <header className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid var(--line)', paddingBottom: 18 }}>
        <div className="col" style={{ gap: 6 }}>
          <div className="kicker">insights · what iris has noticed</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 64, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
            {data.length} patterns,<br /><span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>{newCount} new.</span>
          </h1>
        </div>
      </header>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
        {data.map(i => <Card key={i.id} insight={i} onOpen={(id) => nav(`/insights/${id}`)} />)}
      </div>
    </div>
  );
}

// ─── Detail ───────────────────────────────────────────────────────────────

function TwinSeries({ ev }: { ev: Extract<InsightEvidence, { kind: 'twin-series' }> }) {
  const W = 700, H = 220;
  const all = ev.series.flatMap(s => s.points.map(p => p.y));
  const min = Math.min(...all), max = Math.max(...all), span = max - min || 1;
  const xFor = (i: number, n: number) => (i / (n - 1)) * W;
  const yFor = (v: number) => 20 + (1 - (v - min) / span) * (H - 40);
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`}>
      {[0, 0.25, 0.5, 0.75, 1].map((p, i) => <line key={i} x1="0" y1={20 + p * (H - 40)} x2={W} y2={20 + p * (H - 40)} stroke="var(--line-soft)" strokeDasharray="2 4" />)}
      {ev.series.map((s, si) => {
        const path = s.points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xFor(i, s.points.length)} ${yFor(p.y)}`).join(' ');
        return (
          <g key={si}>
            <path d={path} stroke={color(s.color)} strokeWidth="1.8" fill="none" strokeDasharray={si === 1 ? '4 3' : undefined} />
            {s.points.map((p, i) => <circle key={i} cx={xFor(i, s.points.length)} cy={yFor(p.y)} r="2.5" fill={color(s.color)} />)}
            <text x={6 + si * 120} y="14" fontFamily="var(--mono)" fontSize="9" fill={color(s.color)} letterSpacing="0.08em">{si === 0 ? '—' : '---'} {s.name.toUpperCase()}</text>
          </g>
        );
      })}
    </svg>
  );
}

function DetailView() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, isError, refetch } = useInsight(id);
  const nav = useNavigate();

  if (isLoading) return <LoadingState />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;
  if (!data) return <EmptyState title="Insight not found." action={<button className="btn" onClick={() => nav('/insights')}>← back to insights</button>} />;

  const c = color(data.accentColor);
  const twin = data.evidence.find(e => e.kind === 'twin-series') as Extract<InsightEvidence, { kind: 'twin-series' }> | undefined;
  const comp = data.evidence.find(e => e.kind === 'comparison') as Extract<InsightEvidence, { kind: 'comparison' }> | undefined;

  return (
    <div style={{ padding: '0 0 48px' }}>
      <div className="row" style={{ alignItems: 'center', justifyContent: 'space-between', padding: '20px 40px', borderBottom: '1px solid var(--line-soft)' }}>
        <button className="btn ghost" onClick={() => nav('/insights')} style={{ color: 'var(--ink-3)' }}>← all insights</button>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn">▷ ask iris about this</button>
          <button className="btn">snooze 30d</button>
          <button className="btn">mark resolved</button>
        </div>
      </div>

      <article style={{ padding: '36px 60px 24px', borderBottom: '1px solid var(--line)' }}>
        <div className="row" style={{ gap: 10, marginBottom: 14 }}>
          {data.featured && <span className="tag" style={{ color: 'var(--sage)', borderColor: 'var(--sage-dim)' }}>★ featured</span>}
          {data.tags.map((t, i) => <span key={i} className="tag">{t}</span>)}
        </div>
        <h1 className="serif" style={{ margin: 0, fontSize: 88, lineHeight: 0.92, letterSpacing: '-0.03em' }}>
          {data.headline.line1}<br /><span style={{ color: c }}>{data.headline.line2}</span><br />
          <span style={{ fontStyle: 'italic', color: 'var(--ink-2)' }}>{data.headline.line3}</span>
        </h1>
        <p style={{ marginTop: 24, fontSize: 18, lineHeight: 1.55, color: 'var(--ink-2)', maxWidth: 820, fontFamily: 'var(--serif)' }}>{data.summary}</p>
      </article>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 36, padding: '32px 60px' }}>
        <div className="col" style={{ gap: 32 }}>
          {twin && (
            <section>
              <div className="kicker">{twin.label}</div>
              <h3 className="serif" style={{ margin: '6px 0 16px', fontSize: 24 }}>The evidence.</h3>
              <TwinSeries ev={twin} />
            </section>
          )}
          {comp && (
            <section>
              <div className="kicker">{comp.label}</div>
              <div className="row" style={{ gap: 24, padding: '20px 0', alignItems: 'flex-end', borderTop: '1px solid var(--line-soft)' }}>
                {comp.items.map((it, i) => (
                  <div key={i} className="col" style={{ alignItems: 'flex-start', gap: 4 }}>
                    <div className="numerals" style={{ fontSize: 72, color: i === 0 ? c : 'var(--ink)' }}>
                      {it.value > 0 && comp.items[0] === it ? '+' : ''}{it.value}{it.sub && <span style={{ fontSize: 16, color: 'var(--ink-3)', letterSpacing: '0.06em', marginLeft: 4 }}>{it.sub}</span>}
                    </div>
                    <div className="kicker">{it.label}</div>
                  </div>
                ))}
              </div>
            </section>
          )}
          <section>
            <div className="kicker">in your own words</div>
            <h3 className="serif" style={{ margin: '6px 0 16px', fontSize: 24 }}>Pull quotes.</h3>
            <div className="col" style={{ gap: 14 }}>
              {data.pullQuotes.map((q, i) => (
                <blockquote key={i} style={{ margin: 0, padding: '0 0 0 18px', borderLeft: `2px solid ${c}` }}>
                  <div className="serif" style={{ fontSize: 19, fontStyle: 'italic', lineHeight: 1.4, color: 'var(--ink)' }}>"{q.text}"</div>
                  <div style={{ marginTop: 6, fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{q.sourceDate} · {q.sourceKind}</div>
                </blockquote>
              ))}
            </div>
          </section>
        </div>

        <aside className="col" style={{ gap: 28 }}>
          <section style={{ padding: '20px 22px', background: 'var(--bg-2)', border: '1px solid var(--line-soft)', borderRadius: 10 }}>
            <div className="row" style={{ gap: 10, alignItems: 'center', marginBottom: 10 }}>
              <div className="iris-orb sm" />
              <span className="kicker">iris's read</span>
            </div>
            <div className="serif ital" style={{ fontSize: 18, lineHeight: 1.4, color: 'var(--ink)' }}>"{data.irisRead}"</div>
          </section>
          <section>
            <div className="kicker" style={{ marginBottom: 8 }}>things to try</div>
            <div className="col" style={{ gap: 10 }}>
              {data.suggestions.map(s => (
                <button key={s.id} className="col" style={{ alignItems: 'flex-start', gap: 4, background: 'transparent', border: '1px solid var(--line)', borderRadius: 8, padding: '10px 14px', textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit', color: 'inherit' }}>
                  <span style={{ fontSize: 13, color: 'var(--ink)' }}>{s.label}</span>
                  <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>{s.impact}</span>
                </button>
              ))}
            </div>
          </section>
          <section>
            <div className="kicker" style={{ marginBottom: 10 }}>related</div>
            <div className="col" style={{ gap: 8 }}>
              {data.related.map(r => (
                <div key={r.id} className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between', cursor: 'pointer' }} onClick={() => nav(`/insights/${r.id}`)}>
                  <span style={{ fontSize: 13, color: 'var(--ink-2)' }}>{r.label}</span>
                  <span className="tag">{r.tag}</span>
                </div>
              ))}
            </div>
          </section>
          <section style={{ paddingTop: 14, borderTop: '1px dashed var(--line)' }}>
            <div className="kicker" style={{ marginBottom: 6 }}>how iris found this</div>
            <div style={{ fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.55, fontStyle: 'italic' }}>{data.methodology}</div>
          </section>
        </aside>
      </div>
    </div>
  );
}

export function InsightsScreen() {
  const { id } = useParams<{ id: string }>();
  return id ? <DetailView /> : <IndexView />;
}

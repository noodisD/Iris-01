import React from 'react';
import { useReview } from '@/hooks/useData';
import { LoadingState, ErrorState } from '@/components/states';

/** Render a delta with its real sign — a hardcoded '+' turned -1.2 into '+-1.2'. */
const signed = (n: number) => (n > 0 ? `+${n}` : `${n}`);

/** Cinematic weekly review — Iris's letter + numbers + word-poem. */
export function ReviewScreen() {
  const { data, isLoading, isError, refetch } = useReview();
  if (isLoading) return <LoadingState label="Iris is composing your week…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  const m = data.metrics;
  return (
    <div className="col" style={{ minHeight: '100%' }}>
      <div className="row" style={{ alignItems: 'center', justifyContent: 'space-between', padding: '20px 56px', borderBottom: '1px solid var(--line-soft)' }}>
        <span className="kicker">your week · {data.weekStart} — {data.weekEnd}</span>
        <button className="btn primary">▷ Read aloud · 2 min</button>
      </div>

      <section style={{ flex: 1, padding: '90px 0 56px', display: 'flex', flexDirection: 'column', alignItems: 'center', background: 'radial-gradient(ellipse at top, rgba(169,200,163,0.04) 0%, transparent 70%)' }}>
        <div className="iris-orb" style={{ marginBottom: 28 }} />
        <div style={{ maxWidth: 760, padding: '0 56px' }}>
          <div className="kicker" style={{ marginBottom: 18, textAlign: 'center' }}>iris's letter</div>
          {data.letter.split('\n\n').map((para, i) => (
            <div key={i} className="serif" style={{
              fontSize: i === 0 ? 48 : 26, lineHeight: i === 0 ? 1.05 : 1.5,
              letterSpacing: '-0.01em', color: i === 0 ? 'var(--ink)' : 'var(--ink-2)',
              marginTop: i === 0 ? 0 : 22, fontStyle: i === 0 ? 'normal' : 'italic', textWrap: 'pretty',
            }}>{para}</div>
          ))}
        </div>

        <div className="row" style={{ gap: 48, marginTop: 64, padding: '32px 56px 0', borderTop: '1px dashed var(--line)', maxWidth: 760, width: '100%' }}>
          {[
            { v: m.energyAvg.toFixed(1), l: `energy · ${signed(m.energyDelta)}`, c: 'var(--sage)' },
            { v: `${m.habitsHit}/${m.habitsTotal}`, l: 'habits hit', c: 'var(--ink)' },
            { v: String(m.winsLogged), l: 'wins logged', c: 'var(--amber)' },
          ].map((s, i) => (
            <div key={i} className="col" style={{ gap: 2 }}>
              <span className="numerals" style={{ fontSize: 40, color: s.c }}>{s.v}</span>
              <span className="kicker">{s.l}</span>
            </div>
          ))}
        </div>
      </section>

      <section style={{ padding: '40px 56px 30px', borderTop: '1px solid var(--line-soft)' }}>
        <div className="kicker" style={{ marginBottom: 24, textAlign: 'center' }}>· seven words for seven days ·</div>
        <div className="row" style={{ justifyContent: 'space-between', gap: 14, maxWidth: 1080, margin: '0 auto', alignItems: 'flex-end' }}>
          {data.days.map((d, i) => {
            const intensity = d.energy / 10;
            return (
              <div key={i} className="col" style={{ alignItems: 'center', gap: 10, flex: 1 }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>{d.shortName}</span>
                <div style={{ width: 8 + intensity * 32, height: 8 + intensity * 32, borderRadius: '50%', background: 'radial-gradient(circle at 35% 30%, var(--orb-hue-a), var(--orb-hue-b) 55%, var(--orb-hue-c) 100%)', opacity: 0.5 + intensity * 0.5 }} />
                <span className="serif" style={{ fontSize: 22, fontStyle: 'italic', color: 'var(--ink)' }}>{d.word}</span>
              </div>
            );
          })}
        </div>
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', padding: '32px 56px 48px', borderTop: '1px solid var(--line-soft)' }}>
        <div className="col" style={{ gap: 8, padding: '0 32px 0 0' }}>
          <div className="kicker">three themes</div>
          <ol style={{ margin: 0, paddingLeft: 22, color: 'var(--ink)' }}>
            {data.themes.map((t, i) => <li key={i} className="serif" style={{ fontSize: 18, fontStyle: 'italic', lineHeight: 1.4, marginBottom: 6, color: i === 0 ? 'var(--ink)' : 'var(--ink-2)' }}>{t}</li>)}
          </ol>
        </div>
        <div className="col" style={{ gap: 8, padding: '0 32px', borderLeft: '1px dashed var(--line)' }}>
          <div className="kicker">the win that mattered</div>
          <div className="serif" style={{ fontSize: 22, fontStyle: 'italic', lineHeight: 1.3, color: 'var(--ink)' }}>"{data.winThatMattered}"</div>
        </div>
        <div className="col" style={{ gap: 8, padding: '0 0 0 32px', borderLeft: '1px dashed var(--line)' }}>
          <div className="kicker">looking ahead</div>
          {data.lookahead.map((l, i) => (
            <div key={i} className="row" style={{ gap: 8, alignItems: 'baseline' }}>
              <span style={{ width: 80, fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>{l.when}</span>
              <span style={{ fontSize: 12, color: 'var(--ink)' }}>{l.what}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

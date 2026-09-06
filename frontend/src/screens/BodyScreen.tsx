import React from 'react';
import { useBody } from '@/hooks/useData';
import { LoadingState, ErrorState } from '@/components/states';
import { Sparkline, Ring } from '@/components/primitives';

/**
 * Body screen — wired to useBody(). This is a faithful-but-compact port;
 * the full prototype (screens/body.jsx) has the hypnogram + fusion chart
 * that should be ported here next. Marked PARTIAL.
 */
export function BodyScreen() {
  const { data, isLoading, isError, refetch } = useBody();
  if (isLoading) return <LoadingState label="Iris is reading your Air…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  const latest = data.recent[data.recent.length - 1];
  const hrvSeries = data.recent.map(d => d.hrvMs);
  const readinessSeries = data.recent.map(d => d.readiness);

  return (
    <div className="col" style={{ padding: '24px 32px 40px', gap: 24 }}>
      <header className="row" style={{ alignItems: 'flex-end', justifyContent: 'space-between', borderBottom: '1px solid var(--line)', paddingBottom: 16 }}>
        <div className="col" style={{ gap: 6 }}>
          <div className="kicker">body · what the air heard</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 56, letterSpacing: '-0.025em', lineHeight: 1 }}>
            Your body, in <span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>signals</span>.
          </h1>
        </div>
        <div className="col" style={{ gap: 2, alignItems: 'flex-end' }}>
          <span style={{ fontSize: 13, color: 'var(--ink)' }}>{data.source.label}</span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--sage)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            {data.source.connected ? '● synced' : '○ offline'} · {data.source.batteryPct ?? '—'}%
          </span>
        </div>
      </header>

      <section style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 32, padding: '8px 0 16px' }}>
        <div className="col" style={{ gap: 8 }}>
          <div className="kicker">today's readiness</div>
          <div className="row" style={{ gap: 24, alignItems: 'flex-end' }}>
            <div className="numerals" style={{ fontSize: 140, color: latest.readiness > 70 ? 'var(--sage)' : 'var(--amber)', letterSpacing: '-0.04em', lineHeight: 0.82 }}>{latest.readiness}</div>
            <div className="col" style={{ gap: 4, paddingBottom: 18 }}>
              <span className="kicker">/ 100</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-3)' }}>14-day avg · {data.rollups.avgReadiness14d}</span>
            </div>
          </div>
          <Sparkline data={readinessSeries} w={460} h={36} stroke="var(--sage)" baseline />
        </div>
        <div className="col" style={{ gap: 14, paddingLeft: 32, borderLeft: '1px dashed var(--line)' }}>
          <div className="row" style={{ gap: 10, alignItems: 'center' }}>
            <div className="iris-orb sm" />
            <span className="kicker">iris translates</span>
          </div>
          <div className="serif ital" style={{ fontSize: 22, lineHeight: 1.4, color: 'var(--ink)' }}>
            "Your HRV is {latest.hrvMs} ms against a {data.rollups.hrvBaselineMs} baseline. The Air says you have more in the tank than your words admit."
          </div>
        </div>
      </section>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
        {[
          { label: 'HRV · 14 nights', value: `${latest.hrvMs}`, unit: 'MS', series: hrvSeries, c: 'var(--sage)' },
          { label: 'Resting HR', value: `${latest.rhrBpm}`, unit: 'BPM', series: data.recent.map(d => d.rhrBpm), c: 'var(--rose)' },
          { label: 'Breathing', value: `${latest.breathingRate}`, unit: 'BR/M', series: data.recent.map(d => d.breathingRate), c: 'var(--indigo)' },
        ].map((card, i) => (
          <div key={i} style={{ background: 'var(--bg-2)', border: '1px solid var(--line-soft)', borderRadius: 10, padding: '18px 20px' }}>
            <div className="kicker" style={{ marginBottom: 10 }}>{card.label}</div>
            <div className="numerals" style={{ fontSize: 48, color: card.c }}>{card.value}<span style={{ fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--ink-3)', letterSpacing: '0.06em', marginLeft: 6 }}>{card.unit}</span></div>
            <div style={{ marginTop: 10 }}><Sparkline data={card.series} w={300} h={40} stroke={card.c} fill /></div>
          </div>
        ))}
      </div>

      <p style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
        PARTIAL PORT · hypnogram + HRV↔anxiety fusion chart to be ported from prototype screens/body.jsx
      </p>
    </div>
  );
}

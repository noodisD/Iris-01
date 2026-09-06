import React from 'react';
import { useHabits } from '@/hooks/useHabits';
import { useInsights } from '@/hooks/useInsights';
import { useNavigate } from 'react-router-dom';

/**
 * Today / dashboard — composed from multiple hooks.
 * PARTIAL: the full prototype (screens/dashboard.jsx) has ~12 cards
 * (mood, energy, sleep bars, anxiety heatmap, topics, correlations…).
 * This shows the headline + a representative subset wired to real data;
 * port remaining cards as the backend exposes those series.
 */
export function TodayScreen() {
  const { data: habits } = useHabits();
  const { data: insights } = useInsights();
  const nav = useNavigate();

  const featured = insights?.find(i => i.featured);

  return (
    <div className="col" style={{ padding: '24px 32px 40px', gap: 24 }}>
      <header className="row" style={{ alignItems: 'flex-end', justifyContent: 'space-between', borderBottom: '1px solid var(--line)', paddingBottom: 16 }}>
        <div className="col" style={{ gap: 4 }}>
          <div className="kicker">today · at a glance</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 56, letterSpacing: '-0.025em', lineHeight: 1 }}>
            Today's reading<span style={{ color: 'var(--sage)' }}>.</span>
          </h1>
        </div>
        <button className="btn primary" onClick={() => nav('/chat')}>▷ Daily check-in</button>
      </header>

      {featured && (
        <div className="row" style={{ gap: 18, alignItems: 'flex-start', padding: '8px 0 12px', borderBottom: '1px dashed var(--line)', cursor: 'pointer' }} onClick={() => nav(`/insights/${featured.id}`)}>
          <div className="iris-orb" style={{ marginTop: 6 }} />
          <div className="col" style={{ flex: 1, gap: 4 }}>
            <div className="kicker">iris, just now</div>
            <div className="serif" style={{ fontSize: 26, fontStyle: 'italic', lineHeight: 1.3, color: 'var(--ink)', maxWidth: 880 }}>
              "{featured.summary}"
            </div>
          </div>
          <span className="btn" style={{ alignSelf: 'flex-start' }}>↗ open</span>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
        {habits && (
          <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-soft)', borderRadius: 10, padding: '18px 20px' }}>
            <div className="kicker" style={{ marginBottom: 10 }}>Habits · today</div>
            <div className="numerals" style={{ fontSize: 56, color: 'var(--ink)' }}>{habits.doneCount}<span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink-3)', marginLeft: 6 }}>/{habits.totalCount}</span></div>
            <div className="col" style={{ gap: 6, marginTop: 12 }}>
              {habits.habits.slice(0, 4).map(h => (
                <div key={h.id} className="row" style={{ alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: h.doneToday ? 'var(--sage)' : 'var(--line)' }} />
                  <span style={{ fontSize: 12, color: h.doneToday ? 'var(--ink)' : 'var(--ink-3)' }}>{h.name}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <p style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
        PARTIAL PORT · mood/energy/sleep/anxiety-heatmap/topics/correlations cards to be ported from prototype screens/dashboard.jsx
      </p>
    </div>
  );
}

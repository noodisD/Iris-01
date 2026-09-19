import { useHabits } from '@/hooks/useHabits';
import { useInsights } from '@/hooks/useInsights';
import { useNavigate } from 'react-router-dom';
import { LoadingState, ErrorState } from '@/components/states';

/** Today: the featured finding, if there is one, and today's habits. */
export function TodayScreen() {
  const habitsQuery = useHabits();
  const insightsQuery = useInsights();
  const nav = useNavigate();

  if (habitsQuery.isLoading || insightsQuery.isLoading) return <LoadingState />;
  if (habitsQuery.isError && insightsQuery.isError) {
    return <ErrorState onRetry={() => { habitsQuery.refetch(); insightsQuery.refetch(); }} />;
  }

  const habits = habitsQuery.data;
  const featured = insightsQuery.data?.find(i => i.featured);

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
            {/* The measurement, not a time: a featured finding can be a count
                across two years, and "just now" said otherwise. */}
            <div className="kicker">iris · {featured.kind}</div>
            <div className="serif" style={{ fontSize: 26, fontStyle: 'italic', lineHeight: 1.3, color: 'var(--ink)', maxWidth: 880 }}>
              "{featured.summary}"
            </div>
          </div>
          <span className="btn" style={{ alignSelf: 'flex-start' }}>↗ open</span>
        </div>
      )}

      {insightsQuery.isError && <Unavailable what="Findings" retry={() => insightsQuery.refetch()} />}
      {habitsQuery.isError && <Unavailable what="Habits" retry={() => habitsQuery.refetch()} />}

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

    </div>
  );
}

function Unavailable({ what, retry }: { what: string; retry: () => void }) {
  return (
    <div className="row" role="alert" style={{ gap: 12, alignItems: 'baseline', color: 'var(--ink-3)', fontSize: 13 }}>
      <span>{what} didn't load. Nothing is lost — this is only the view.</span>
      <button className="btn" onClick={retry}>retry</button>
    </div>
  );
}

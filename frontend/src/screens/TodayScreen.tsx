import { useHabits } from '@/hooks/useHabits';
import { usePatterns } from '@/hooks/usePatterns';
import { useNavigate } from 'react-router-dom';
import { LoadingState, ErrorState } from '@/components/states';
import type { PatternSummary } from '@/types/api';

/**
 * The pattern most worth a look: the one found on the most occasions that you
 * have not yet said rings true or not. It is offered as a question, because
 * whether a pattern holds for you is yours to say.
 */
export function nextPattern(patterns: PatternSummary[] | undefined): PatternSummary | undefined {
  return (patterns ?? [])
    .filter(p => p.occasions > 0 && !p.verdict)
    .sort((a, b) => b.occasions - a.occasions || a.name.localeCompare(b.name))[0];
}

/** Today: a pattern waiting for your verdict, if there is one, and today's habits. */
export function TodayScreen() {
  const habitsQuery = useHabits();
  const patternsQuery = usePatterns();
  const nav = useNavigate();

  if (habitsQuery.isLoading || patternsQuery.isLoading) return <LoadingState />;
  if (habitsQuery.isError && patternsQuery.isError) {
    return <ErrorState onRetry={() => { habitsQuery.refetch(); patternsQuery.refetch(); }} />;
  }

  const habits = habitsQuery.data;
  const featured = nextPattern(patternsQuery.data?.patterns);

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
        <div className="row" style={{ gap: 18, alignItems: 'flex-start', padding: '8px 0 12px', borderBottom: '1px dashed var(--line)', cursor: 'pointer' }} onClick={() => nav(`/patterns/${featured.id}`)}>
          <div className="iris-orb" style={{ marginTop: 6 }} />
          <div className="col" style={{ flex: 1, gap: 4 }}>
            <div className="kicker">pattern · {featured.occasions} occasions in your writing · does it ring true?</div>
            <div className="serif" style={{ fontSize: 26, fontStyle: 'italic', lineHeight: 1.3, color: 'var(--ink)', maxWidth: 880 }}>
              {featured.name}
            </div>
            <div style={{ fontSize: 13, color: 'var(--ink-3)', maxWidth: 880 }}>{featured.statement}</div>
          </div>
          <span className="btn" style={{ alignSelf: 'flex-start' }}>↗ open</span>
        </div>
      )}

      {patternsQuery.isError && <Unavailable what="Patterns" retry={() => patternsQuery.refetch()} />}
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

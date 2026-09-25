import { Link } from 'react-router-dom';
import { useDifferences, useDifferenceVerdict } from '@/hooks/usePatterns';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import type { Difference, PatternVerdictValue } from '@/types/api';

/**
 * Insights: differences in outcome.
 *
 * Patterns shows what keeps coming up. This shows what goes with it going
 * better or worse: among one pattern's occasions, another pattern that was
 * there more often on one side than the other. Each is a difference between
 * two sets of occasions from the labelling, never a cause and never advice.
 * Whether it rings true is the owner's to say.
 */

const VERDICTS: { value: PatternVerdictValue; label: string }[] = [
  { value: 'rings_true', label: 'rings true' },
  { value: 'does_not', label: "doesn't ring true" },
  { value: 'unsure', label: 'unsure' },
];

/** "3 of 4 times it went worse", read as a sentence about the other pattern. */
export function sentence(d: Difference): { lead: string; worse: string; better: string } {
  return {
    lead: `When ${d.patternName.toLowerCase()} came up,`,
    worse: `${d.otherName.toLowerCase()} was there ${d.worse} of ${d.worseTotal} times it went worse`,
    better: `and ${d.better} of ${d.betterTotal} times it went better.`,
  };
}

export function InsightsScreen() {
  const { data, isPending, isError, refetch } = useDifferences();
  if (isPending) return <LoadingState label="Iris is comparing the occasions…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;
  const open = data.differences.filter(d => !d.verdict);
  const judged = data.differences.filter(d => d.verdict);

  return (
    <div className="col" style={{ padding: '24px 32px 40px', gap: 20, maxWidth: 980 }}>
      <header className="col" style={{ gap: 6, borderBottom: '1px solid var(--line)', paddingBottom: 16 }}>
        <div className="kicker">insights · differences in outcome</div>
        <h1 className="serif" style={{ margin: 0, fontSize: 48, lineHeight: 1, letterSpacing: '-0.02em' }}>
          What goes with it going worse<span style={{ color: 'var(--sage)' }}>.</span>
        </h1>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--ink-3)', maxWidth: 720, lineHeight: 1.55 }}>
          For each pattern in your writing, the other patterns that were there more often when it went one way than
          the other. A difference, not a cause: say whether it rings true.
        </p>
      </header>

      {data.differences.length === 0 ? (
        <EmptyState title="No differences yet."
          body="An insight needs a pattern with occasions that went both better and worse, and another pattern that sits on one side by two or more." />
      ) : (
        <>
          {open.map(d => <InsightCard key={`${d.patternId}/${d.otherId}`} d={d} />)}
          {judged.length > 0 && <div className="kicker" style={{ marginTop: 8 }}>judged · {judged.length}</div>}
          {judged.map(d => <InsightCard key={`${d.patternId}/${d.otherId}`} d={d} />)}
        </>
      )}
    </div>
  );
}

function InsightCard({ d }: { d: Difference }) {
  const verdict = useDifferenceVerdict();
  const s = sentence(d);
  const current = d.verdict?.verdict ?? null;
  return (
    <article aria-label={`${d.patternName} and ${d.otherName}`} className="col"
      style={{ gap: 10, padding: '16px 18px', border: '1px solid var(--line)', borderRadius: 10,
               opacity: current === 'does_not' ? 0.55 : 1 }}>
      <div className="serif" style={{ fontSize: 21, lineHeight: 1.35, color: 'var(--ink)' }}>
        {s.lead} <em>{s.worse}</em>, {s.better}
      </div>
      <div className="row" style={{ gap: 14, fontSize: 12, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <Link to={`/patterns/${d.patternId}`} style={{ color: 'var(--sage)' }}>{d.patternName} →</Link>
        <Link to={`/patterns/${d.otherId}`} style={{ color: 'var(--ink-3)' }}>{d.otherName} →</Link>
        {d.patternVerdict?.verdict === 'does_not' && (
          <span style={{ color: 'var(--ink-4)' }}>you said {d.patternName.toLowerCase()} doesn't ring true</span>
        )}
      </div>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
        {VERDICTS.map(v => (
          <button key={v.value} aria-pressed={current === v.value} disabled={verdict.isPending}
            onClick={() => verdict.mutate({ patternId: d.patternId, otherId: d.otherId, verdict: v.value })}
            style={{ fontFamily: 'var(--mono)', fontSize: 11, padding: '3px 9px', borderRadius: 999, cursor: 'pointer',
                     border: `1px solid ${current === v.value ? 'var(--sage)' : 'var(--line)'}`,
                     background: current === v.value ? 'var(--sage)' : 'transparent',
                     color: current === v.value ? '#14140f' : 'var(--ink-3)' }}>
            {v.label}
          </button>
        ))}
      </div>
    </article>
  );
}

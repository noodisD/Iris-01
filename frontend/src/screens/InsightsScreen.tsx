import { Link } from 'react-router-dom';
import { useDayDifferences, useDayDifferenceVerdict, useDifferences, useDifferenceVerdict } from '@/hooks/usePatterns';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import type { DayDifference, Difference, PatternVerdictValue } from '@/types/api';
import { Badge, ChoiceGroup, Page, Panel } from '@/ui';
import styles from './InsightsScreen.module.css';

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
  { value: 'rings_true', label: 'Rings true' },
  { value: 'does_not', label: "Doesn't ring true" },
  { value: 'unsure', label: 'Unsure' },
];

/**
 * Both sides counted, with the patterns named as names: "When a signal arrived
 * and was acted on, or was not came up" is what dropping a name into a clause
 * produced.
 */
export function sentence(d: Difference): string {
  const times = (n: number) => `${n} ${n === 1 ? 'time' : 'times'}`;
  return `Of the ${times(d.worseTotal)} \u201c${d.patternName}\u201d went worse, \u201c${d.otherName}\u201d was there in `
    + `${d.worse}; of the ${times(d.betterTotal)} it went better, in ${d.better}.`;
}

export function InsightsScreen() {
  return (
    <Page title="Insights" width="standard"
      description="What goes with a pattern going better or worse, from your writing and from measured days. Each is a difference, never a cause: say whether it rings true.">
      <PatternDifferencesSection />
      <DayDifferencesSection />
    </Page>
  );
}

function Judged({ count }: { count: number }) {
  return count > 0 ? <h3 className={styles.judged}>Judged ({count})</h3> : null;
}

function PatternDifferencesSection() {
  const { data, isPending, isError, refetch } = useDifferences();
  const open = data?.differences.filter(d => !d.verdict) ?? [];
  const judged = data?.differences.filter(d => d.verdict) ?? [];

  return (
    <section aria-label="Writing differences" className={styles.section}>
      <h2 className={styles.heading}>From your writing</h2>
      {isPending ? <LoadingState label="Iris is comparing the occasions…" />
        : isError || !data ? <ErrorState onRetry={() => refetch()} />
        : data.differences.length === 0 ? (
          <EmptyState title="No differences yet."
            body="An insight needs a pattern with occasions that went both better and worse, and another pattern that sits on one side by two or more." />
        ) : (
        <>
          {open.map(d => <InsightCard key={`${d.patternId}/${d.otherId}`} d={d} />)}
          <Judged count={judged.length} />
          {judged.map(d => <InsightCard key={`${d.patternId}/${d.otherId}`} d={d} />)}
        </>
      )}
    </section>
  );
}

function DayDifferencesSection() {
  const { data, isPending, isError, refetch } = useDayDifferences();
  const open = data?.differences.filter(d => !d.verdict) ?? [];
  const judged = data?.differences.filter(d => d.verdict) ?? [];
  return (
    <section aria-label="Days compared" className={styles.section}>
      <div>
        <h2 className={styles.heading}>Days compared</h2>
        <p className={styles.note}>Your check-ins against days measured by the phone and Timeline.</p>
      </div>
      {isPending ? <LoadingState label="Comparing measured days…" />
        : isError || !data ? <ErrorState onRetry={() => refetch()} />
        : data.differences.length === 0
          ? <EmptyState title="No days to compare yet."
              body="A comparison needs at least five measured days with a check-in on each side of a difference." />
          : <>
              {open.map(d => <DayDifferenceCard key={`${d.outcome}/${d.split}`} d={d} />)}
              <Judged count={judged.length} />
              {judged.map(d => <DayDifferenceCard key={`${d.outcome}/${d.split}`} d={d} />)}
            </>}
    </section>
  );
}

function tone(current: PatternVerdictValue | null): 'confirmed' | 'quiet' | undefined {
  return current === 'rings_true' ? 'confirmed' : current === 'does_not' ? 'quiet' : undefined;
}

function DayDifferenceCard({ d }: { d: DayDifference }) {
  const verdict = useDayDifferenceVerdict();
  const current = d.verdict?.verdict ?? null;
  return (
    <Panel as="article" tone={tone(current)} aria-label={`${d.outcome.replace('_', ' ')} by ${d.split.replace('_', ' ')}`}>
      <p className={styles.sentence}>{d.sentence}</p>
      <div className={styles.meta}>
        <Badge>{d.leftCount} days and {d.rightCount} days compared</Badge>
        <span>p = {d.pValue.toPrecision(2)}</span>
      </div>
      <ChoiceGroup label="Does this ring true?" tone="confirm" options={VERDICTS} value={current}
        disabled={verdict.isPending}
        onChange={value => value && verdict.mutate({ outcome: d.outcome, split: d.split, verdict: value })} />
      {verdict.isError && <p role="alert" className={styles.error}>Verdict not saved. Try again.</p>}
    </Panel>
  );
}

function InsightCard({ d }: { d: Difference }) {
  const verdict = useDifferenceVerdict();

  const current = d.verdict?.verdict ?? null;
  return (
    <Panel as="article" tone={tone(current)} aria-label={`${d.patternName} and ${d.otherName}`}>
      <p className={styles.sentence}>{sentence(d)}</p>
      <div className={styles.meta}>
        <Link to={`/patterns/${d.patternId}`}>{d.patternName}</Link>
        <Link to={`/patterns/${d.otherId}`}>{d.otherName}</Link>
        {d.patternVerdict?.verdict === 'does_not' && (
          <span>You said {d.patternName.toLowerCase()} doesn't ring true.</span>
        )}
      </div>
      <ChoiceGroup label="Does this ring true?" tone="confirm" options={VERDICTS} value={current}
        disabled={verdict.isPending}
        onChange={value => value && verdict.mutate({ patternId: d.patternId, otherId: d.otherId, verdict: value })} />
    </Panel>
  );
}

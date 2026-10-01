import { Link, useNavigate } from 'react-router-dom';
import { useHabits } from '@/hooks/useHabits';
import { usePatterns, usePatternVerdict } from '@/hooks/usePatterns';
import { LoadingState, ErrorState } from '@/components/states';
import { Badge, Button, ChoiceGroup, Page, Panel, Section } from '@/ui';
import type { PersonalPattern, PatternVerdictValue } from '@/types/api';
import styles from './TodayScreen.module.css';

/** The server orders the personal dynamics; a note alone is not a verdict. */
export function nextPattern(patterns: PersonalPattern[] | undefined): PersonalPattern | undefined {
  return patterns?.find(p => !p.feedback?.verdict || p.feedback.needsReview);
}

const VERDICTS: { value: PatternVerdictValue; label: string }[] = [
  { value: 'rings_true', label: 'Rings true' },
  { value: 'does_not', label: "Doesn't" },
  { value: 'unsure', label: 'Unsure' },
];

function today(): string {
  return new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });
}

/** Today: a pattern waiting for your verdict, judged in place, and today's habits. */
export function TodayScreen() {
  const habitsQuery = useHabits();
  const patternsQuery = usePatterns();
  const nav = useNavigate();

  if (habitsQuery.isLoading || patternsQuery.isLoading) return <LoadingState />;
  if (habitsQuery.isError && patternsQuery.isError) {
    return <ErrorState onRetry={() => { habitsQuery.refetch(); patternsQuery.refetch(); }} />;
  }

  const habits = habitsQuery.data;
  const featured = patternsQuery.data?.status.stage === 'ready'
    ? nextPattern(patternsQuery.data.patterns) : undefined;

  return (
    <Page title="Today" lead={today()} width="standard"
      actions={<>
        <Button variant="primary" onClick={() => nav('/chat')}>Start a check-in</Button>
        <Button onClick={() => nav('/journal')}>Write</Button>
      </>}>
      {patternsQuery.isError && <Unavailable what="Patterns" retry={() => patternsQuery.refetch()} />}
      {featured && <PatternToJudge pattern={featured} />}

      {habitsQuery.isError && <Unavailable what="Habits" retry={() => habitsQuery.refetch()} />}
      {habits && (
        <Section title="Habits today" actions={<Link to="/habits">All habits</Link>}>
          {habits.habits.length === 0 ? (
            <p className={styles.quiet}>No habits yet. <Link to="/habits">Add one</Link> to see it here each day.</p>
          ) : (
            <>
              <p className={styles.quiet}>{habits.doneCount} of {habits.totalCount} done</p>
              <ul className={styles.habits}>
                {habits.habits.map(h => (
                  <li key={h.id} className={h.doneToday ? styles.done : undefined}>
                    <span className={styles.check} aria-hidden />
                    {h.name}
                    <span className="visually-hidden">{h.doneToday ? ' (done)' : ' (not done yet)'}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Section>
      )}
    </Page>
  );
}

function PatternToJudge({ pattern }: { pattern: PersonalPattern }) {
  const verdict = usePatternVerdict(pattern.id);
  return (
    <Section title="Does this ring true?"
      description="The first unreviewed personal dynamic in the current checked order.">
      <Panel as="article" aria-label={pattern.title}>
        <div className={styles.patternHead}>
          <div className={styles.patternText}>
            <h3 className={styles.patternName}>{pattern.title}</h3>
            <p className={styles.statement}>{pattern.context.text} → {pattern.response.text}</p>
          </div>
        </div>
        {pattern.feedback?.needsReview && <p>Your saved opinion needs review: the evidence changed.</p>}
        <div className={styles.patternFoot}>
          <Badge>{pattern.evidenceState === 'owner_described' ? 'You described this'
            : `At least ${pattern.independentGroupCount} distinct occasions identified`}</Badge>
          <Link to={`/patterns/${encodeURIComponent(pattern.id)}?range=all`}>See the accounts</Link>
        </div>
        <ChoiceGroup label="Does this pattern ring true?" tone="confirm" options={VERDICTS}
          value={pattern.feedback?.verdict ?? null} clearable
          disabled={verdict.isPending} onChange={value => verdict.mutate({
            range: 'all', snapshot: pattern.snapshot, verdict: value, note: pattern.feedback?.note ?? null,
          })} />
        {pattern.feedback?.needsReview && pattern.feedback.verdict && <Button size="sm"
          disabled={verdict.isPending} onClick={() => verdict.mutate({
            range: 'all', snapshot: pattern.snapshot,
            verdict: pattern.feedback!.verdict, note: pattern.feedback!.note,
          })}>Confirm this opinion on current evidence</Button>}
        {verdict.isError && <p role="alert">Opinion not saved. Review current evidence and try again.</p>}
      </Panel>
    </Section>
  );
}

function Unavailable({ what, retry }: { what: string; retry: () => void }) {
  return (
    <div role="alert" className={styles.unavailable}>
      <span>{what} didn't load. Nothing is lost; this is only the view.</span>
      <Button size="sm" onClick={retry}>Retry</Button>
    </div>
  );
}

import { Link, useNavigate } from 'react-router-dom';
import { useHabits } from '@/hooks/useHabits';
import { usePatterns, usePatternVerdict } from '@/hooks/usePatterns';
import { LoadingState, ErrorState } from '@/components/states';
import { Badge, Button, ChoiceGroup, Lens, Page, Panel, Section } from '@/ui';
import type { PatternSummary, PatternVerdictValue } from '@/types/api';
import styles from './TodayScreen.module.css';

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
  const featured = nextPattern(patternsQuery.data?.patterns);

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

function PatternToJudge({ pattern }: { pattern: PatternSummary }) {
  const verdict = usePatternVerdict(pattern.id);
  return (
    <Section title="Does this ring true?"
      description="The pattern found most often in your writing that you haven't judged yet.">
      <Panel as="article" aria-label={pattern.name}>
        <div className={styles.patternHead}>
          <Lens size={28} />
          <div className={styles.patternText}>
            <h3 className={styles.patternName}>{pattern.name}</h3>
            <p className={styles.statement}>{pattern.statement}</p>
          </div>
        </div>
        <div className={styles.patternFoot}>
          <Badge>{pattern.occasions} occasions in your writing</Badge>
          <Link to={`/patterns/${pattern.id}`}>See the occasions</Link>
        </div>
        <ChoiceGroup label="Does this pattern ring true?" tone="confirm" options={VERDICTS} value={null}
          disabled={verdict.isPending} onChange={value => value && verdict.mutate(value)} />
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

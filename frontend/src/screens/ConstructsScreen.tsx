import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  useConfirmConstruct, useConstructCandidates, useDiscoverConstructs, useLastRun, useRejectConstruct,
} from '@/hooks/useConstructs';
import { LoadingState, ErrorState, EmptyState } from '@/components/states';
import { formatEventDate, DAY_LONG } from '@/lib/dates';
import type { ConstructCandidate, DiscoveryRun } from '@/types/api';
import { Badge, Button, Page, Panel } from '@/ui';
import styles from './ConstructsScreen.module.css';

function Candidate({ c }: { c: ConstructCandidate }) {
  const confirm = useConfirmConstruct();
  const reject = useRejectConstruct();
  const nav = useNavigate();
  const busy = confirm.isPending || reject.isPending;

  const span = c.spanStart && c.spanEnd
    ? `${formatEventDate(c.spanStart, DAY_LONG)} to ${formatEventDate(c.spanEnd, DAY_LONG)}`
    : null;

  return (
    <Panel as="article" aria-label={c.claim}>
      {(confirm.isError || reject.isError) && (
        // Without this the buttons simply became usable again, which reads as
        // a misclick rather than as a decision that did not reach the server.
        <p role="alert" className={styles.error}>That didn't save. The pattern is still waiting for your decision.</p>
      )}

      <header className={styles.head}>
        <div className={styles.badges}>
          <Badge>{c.claimKind === 'behaviour' ? 'Claims something happened' : 'Counts what you wrote about'}</Badge>
          {span && <span className={styles.span}>{span}</span>}
        </div>
        <h2 className={styles.claim}>{c.claim}</h2>
      </header>

      {/* The quotes are the point. Confirming means reading the sentences the
          claim rests on, not taking a model's word for the claim. */}
      <section aria-label="In your own words" className={styles.quotes}>
        <h3 className={styles.quotesTitle}>In your own words</h3>
        {c.quotes.map((q, i) => (
          <blockquote key={i} className={styles.quote}>
            <p>&ldquo;{q.text}&rdquo;</p>
            {q.citable && q.entryId
              ? <Button variant="quiet" size="sm" onClick={() => nav(`/journal?entry=${q.entryId}`)}>Read the entry</Button>
              : <span className={styles.uncounted}>From a recording, undated, so it is never counted</span>}
          </blockquote>
        ))}
      </section>

      <footer className={styles.foot}>
        <p className={styles.explain}>Counts how often this comes up in what you wrote. Not how often you did it.</p>
        <div className={styles.actions}>
          <Button disabled={busy} onClick={() => reject.mutate(c.id)}>{reject.isPending ? 'Setting aside…' : 'Not me'}</Button>
          <Button variant="primary" disabled={busy} onClick={() => confirm.mutate(c.id)}>
            {confirm.isPending ? 'Counting…' : 'Count this in my writing'}
          </Button>
        </div>
      </footer>
    </Panel>
  );
}

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/**
 * What the last read found and why the rest was let go. The support check
 * fails closed, so a model that answers badly empties this screen; without
 * these counts that looked exactly like an archive with nothing to say.
 */
export function RunSummary({ run }: { run: DiscoveryRun }) {
  const d = run.dropped;
  const unchecked = d.unchecked + d.incomplete;
  const letGo = [
    d.mergedAway && `${d.mergedAway} merged into another`,
    unchecked && `${unchecked} because support could not be checked`,
    d.denied && `${d.denied} because a quote denied the claim`,
    d.tooFewSupporting && `${d.tooFewSupporting} with too few supporting quotes`,
    d.alreadyDecided && `${d.alreadyDecided} you had already decided on`,
    d.notEmbedded && `${d.notEmbedded} that could not be stored`,
  ].filter(Boolean) as string[];

  return (
    <p role="status" className={styles.run}>
      <strong>Last read:</strong> {plural(run.rawFindings, 'finding')}, {plural(run.staged, 'proposal')}.
      {run.status !== 'complete' && ` ${run.passesCompleted} of ${run.passesPlanned} passes finished.`}
      {run.dropsRecorded
        ? letGo.length > 0 && ` Let go: ${letGo.join(', ')}.`
        : ' This read was made before IRIS counted what it let go.'}
    </p>
  );
}

export function ConstructsScreen() {
  const { data, isPending, isError, refetch } = useConstructCandidates();
  const discover = useDiscoverConstructs();
  const { data: lastRun } = useLastRun();
  const [includeStaged, setIncludeStaged] = React.useState(true);

  if (isPending) return <LoadingState label="Iris is fetching what she noticed…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  return (
    <Page title="Noticed" width="standard"
      description={`${data.length} ${data.length === 1 ? 'pattern' : 'patterns'} waiting for your word. Nothing here is counted until you say so.`}
      actions={
        <div className={styles.read}>
          <label className={styles.check}>
            <input type="checkbox" checked={includeStaged} onChange={(e) => setIncludeStaged(e.target.checked)} />
            Include voice recordings
          </label>
          <Button variant="primary" disabled={discover.isPending} onClick={() => discover.mutate(includeStaged)}>
            {discover.isPending ? 'Reading your archive…' : 'Read my archive'}
          </Button>
          <span className={styles.sends}>Sends your entries to the model.</span>
        </div>
      }>
      {lastRun && <RunSummary run={lastRun} />}

      {discover.isError && <p role="alert" className={styles.error}>The read did not finish. Nothing was changed.</p>}

      {data.length === 0 ? (
        <EmptyState
          title="Nothing waiting."
          body="Reading the archive is something you ask for. When Iris finds something that recurs in your writing, it waits here with the quotes it rests on, and counts for nothing until you say so."
        />
      ) : (
        <div className={styles.list}>{data.map((c) => <Candidate key={c.id} c={c} />)}</div>
      )}
    </Page>
  );
}

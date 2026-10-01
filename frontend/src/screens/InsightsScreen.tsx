import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useDayDifferenceDetail, useDayDifferences, useDayDifferenceVerdict,
  useInsightVerdict, usePersonalInsight, usePersonalInsights } from '@/hooks/usePatterns';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { evidenceHref } from '@/lib/evidence';
import type { ContributingDay, DayDifference, DayDiagnostics, DiscoveryRange,
  InsightDetail, PatternVerdict, PatternVerdictValue, PersonalInsight } from '@/types/api';
import { Button, ChoiceGroup, Page, Panel } from '@/ui';
import { AccountEvidence, SourcedClause, VerdictEditor } from './PatternsScreen';
import { DiscoveryStatusStrip } from './DiscoveryStatusStrip';
import { DiscoveryPeriod, InvalidDiscoveryPeriod, useDiscoveryPeriod } from './DiscoveryPeriod';
import styles from './InsightsScreen.module.css';

const VERDICTS: { value: PatternVerdictValue; label: string }[] = [
  { value: 'rings_true', label: 'Rings true' },
  { value: 'does_not', label: "Doesn't ring true" },
  { value: 'unsure', label: 'Unsure' },
];
const kindLabel: Record<PersonalInsight['kind'], string> = {
  function_and_tradeoff: 'Function and tradeoff', contextual_difference: 'Contextual difference',
  shared_concern: 'Shared concern',
};

export function InsightsScreen() {
  const [period, setPeriod] = useDiscoveryPeriod();
  if (!period) return <InvalidDiscoveryPeriod />;
  return <Page title="Insights" width="standard"
    description="Tentative connections drawn from checked writing, alongside independent measured-day differences.">
    <DiscoveryPeriod period={period} onChange={setPeriod} />
    <DiscoveryStatusStrip />
    <WritingSection period={period} />
    <DaySection period={period} />
  </Page>;
}

function WritingSection({ period }: { period: DiscoveryRange }) {
  const { data, isPending, isError, refetch } = usePersonalInsights(period);
  return <section aria-label="Personal insights" className={styles.section}>
    <h2 className={styles.heading}>From your writing</h2>
    {isPending ? <LoadingState label="Opening personal insights…" />
      : isError || !data ? <ErrorState onRetry={() => refetch()} />
      : data.status.stage !== 'ready' ? <p role="status">Writing analysis is not current yet; measured days remain available below.</p>
      : data.insights.length === 0 ? <EmptyState title="No checked personal insights in this range."
          body="A pattern can still be visible without enough evidence for an explanatory insight." />
      : data.insights.map(insight => <InsightCard key={`${period}/${insight.id}`} insight={insight} period={period} />)}
  </section>;
}

function InsightEvidence({ detail, insight }: { detail: InsightDetail; insight: PersonalInsight }) {
  const seen = new Set<string>();
  const groups = Object.entries(detail.groups).flatMap(([dynamicId, rows]) => rows.map(group => ({ dynamicId, group })));
  return <div className={styles.evidence}>
    <SourcedClause clause={insight.observation} accounts={detail.accounts} />
    {(['supportingGroups', 'contraryGroups'] as const).map(kind => <section key={kind}
      aria-label={kind === 'supportingGroups' ? 'Supporting event groups' : 'Contrary event groups'}>
      <h4>{kind === 'supportingGroups' ? 'Supporting event groups' : 'Contrary event groups'} ({insight[kind].length})</h4>
      {insight[kind].map(groupId => groups.filter(row => row.group.id === groupId).map(({ dynamicId, group }) =>
        <div key={`${kind}/${dynamicId}/${groupId}`} className={styles.account}>
          <p>Pattern {dynamicId} · {group.role.replace('_', ' ')} ·
            {' '}{group.independenceUncertain ? 'independence uncertain' : group.independentlyCountable ? 'independently identified' : 'not independently counted'}</p>
          {group.accountIds.filter(id => detail.accounts[id]).map(id => {
            seen.add(id);
            return <AccountEvidence key={id} account={detail.accounts[id]} />;
          })}
        </div>))}
      {insight[kind].length === 0 && <p>None recorded in this checked scope.</p>}
    </section>)}
    <section aria-label="Unknown accounts"><h4>Unknown accounts ({insight.unknownAccountIds.length})</h4>
      {insight.unknownAccountIds.filter(id => detail.accounts[id]).map(id => {
        seen.add(id);
        return <AccountEvidence key={id} account={detail.accounts[id]} />;
      })}
    </section>
    <details><summary>All checked groups and accounts</summary>
      {groups.map(({ dynamicId, group }) => <section key={`${dynamicId}/${group.id}`} className={styles.account}>
        <h4>Pattern {dynamicId} · {group.role.replace('_', ' ')} · {group.accountIds.length} accounts</h4>
        {group.accountIds.filter(id => detail.accounts[id]).map(id => {
          seen.add(id);
          const membership = (detail.memberships[dynamicId] ?? []).find(row => row.accountId === id);
          return <div key={id}><p>Checked role: {membership?.role ?? group.role}
            {membership?.excluded && ' · excluded by your correction'}</p>
            <AccountEvidence account={detail.accounts[id]} /></div>;
        })}
      </section>)}
      {Object.values(detail.accounts).filter(account => !seen.has(account.id)).map(account =>
        <AccountEvidence key={account.id} account={account} />)}
    </details>
  </div>;
}

function InsightCard({ insight, period }: { insight: PersonalInsight; period: DiscoveryRange }) {
  const [open, setOpen] = useState(false);
  const detail = usePersonalInsight(insight.id, period, open);
  const verdict = useInsightVerdict(insight.id);
  return <Panel as="article" aria-label={insight.title}>
    <p className={styles.note}>{kindLabel[insight.kind]} · recorded range {period}</p>
    <h3>{insight.title}</h3>
    <p className={styles.sentence}>{insight.observation.text}</p>
    <section className={styles.interpretation} aria-label="Tentative explanation">
      <h4>One possible explanation</h4><p>{insight.possibleMeaning.text}</p>
      <h4>Another possibility</h4><p>{insight.alternative.text}</p>
      <p>Immediate return: {insight.immediateReturn?.text ?? 'Not recorded'}</p>
      <p>Later cost: {insight.laterCost?.text ?? 'Not recorded'}</p>
    </section>
    {insight.kind === 'contextual_difference' && <p>{insight.leftLabel}: {insight.leftGroupIds?.length ?? 0} groups ·
      {' '}{insight.rightLabel}: {insight.rightGroupIds?.length ?? 0} groups.</p>}
    <p>{insight.question}</p>
    <div className={styles.meta}>
      {insight.dynamicIds.map(id => <Link key={id} to={`/patterns/${encodeURIComponent(id)}?range=${period}`}>See personal pattern</Link>)}
      <Link to={evidenceHref({ kind: 'personal_insight', insightId: insight.id,
        range: period, snapshot: insight.snapshot })}>Explore with Iris</Link>
      <Button size="sm" onClick={() => setOpen(!open)}>{open ? 'Hide evidence' : 'See all evidence'}</Button>
    </div>
    {open && (detail.isPending ? <LoadingState label="Opening checked accounts…" />
      : detail.isError || !detail.data ? <ErrorState onRetry={() => detail.refetch()} />
      : <InsightEvidence detail={detail.data} insight={detail.data.insight} />)}
    <VerdictEditor key={`${insight.id}/${period}/${insight.snapshot}`}
      draftKey={`iris:insight-note:${insight.id}/${period}`}
      initial={insight.feedback} range={period} snapshot={insight.snapshot}
      label="Note about this insight" pending={verdict.isPending} error={verdict.isError}
      onSave={value => verdict.mutate(value, {
        onSuccess: () => sessionStorage.removeItem(`iris:insight-note:${insight.id}/${period}`),
      })} />
  </Panel>;
}

function missingDays(diagnostics: DayDiagnostics): string {
  switch (diagnostics.reason) {
    case 'no_measured_days': return 'No confirmed measured days in this period. Review Sensors.';
    case 'no_checkins': return 'No explicit check-in scores in this period. Review Journal.';
    case 'no_overlap': return 'Measured days and check-ins do not overlap in this period.';
    case 'insufficient_groups': return 'No comparison has five valid days in each group.';
    case 'no_qualifying_difference': return 'The available comparisons did not meet the existing difference and permutation gates.';
    default: return '';
  }
}

function DaySection({ period }: { period: DiscoveryRange }) {
  const { data, isPending, isError, refetch } = useDayDifferences(period);
  return <section aria-label="Measured day differences" className={styles.section}>
    <h2 className={styles.heading}>Measured day differences</h2>
    <p className={styles.note}>Explicit check-ins against confirmed phone measurements; independent of writing analysis.</p>
    {isPending ? <LoadingState label="Comparing measured days…" />
      : isError || !data ? <ErrorState onRetry={() => refetch()} />
      : data.differences.length === 0 ? <EmptyState title="No qualifying day comparison."
          body={`${missingDays(data.diagnostics)} Review Journal and Sensors; no new tracking is required.`} />
      : data.differences.map(d => <DayCard key={`${period}/${d.outcome}/${d.split}`} d={d} period={period} />)}
    {data?.diagnostics && <p className={styles.note}>{data.diagnostics.measuredDays} measured days ·
      {data.diagnostics.checkinDays} check-in days · {data.diagnostics.overlappingDays} overlapping days.
      <Link to="/journal"> Journal</Link> · <Link to="/sensors">Sensors</Link></p>}
  </section>;
}

function DayCard({ d, period }: { d: DayDifference; period: DiscoveryRange }) {
  const feedback = useDayDifferenceVerdict();
  const [open, setOpen] = useState(false);
  const detail = useDayDifferenceDetail(d.outcome, d.split, period, d.snapshot, open);
  return <Panel as="article" aria-label={`${d.outcome.replace('_', ' ')} by ${d.split.replace('_', ' ')}`}>
    <p className={styles.sentence}>{d.outcome.replaceAll('_', ' ')} — {d.leftLabel}: {d.leftMean} across {d.leftCount} days;{' '}
      {d.rightLabel}: {d.rightMean} across {d.rightCount} days.</p>
    <p className={styles.note}>Recorded {d.coverage.recordedFrom}–{d.coverage.recordedTo} · {period}.
      Selected observational comparison; not a cause or a personal rule.</p>
    <div className={styles.meta}>
      <Button size="sm" onClick={() => setOpen(!open)}>{open ? 'Hide days' : 'See contributing days'}</Button>
      <Link to={evidenceHref({ kind: 'day', outcome: d.outcome, split: d.split,
        range: period, snapshot: d.snapshot })}>Explore with Iris</Link>
    </div>
    {open && <section aria-label="Measured-day evidence" className={styles.evidence}>
      {detail.isPending ? <LoadingState label="Opening contributing days…" />
        : detail.isError || !detail.data ? <ErrorState onRetry={() => detail.refetch()} />
        : <>
          <DayGroup title={d.leftLabel} days={detail.data.leftDays} />
          <DayGroup title={d.rightLabel} days={detail.data.rightDays} />
          <details><summary>How calculated</summary>
            <p>Threshold {d.threshold ?? 'office/home'} · permutation p = {d.pValue.toPrecision(2)}.
              At least five days per group, one-point mean gap and p ≤ .01 are required. This is not causal confidence.</p>
            <p>Excluded: {Object.entries(detail.data.excluded).map(([reason, count]) => `${reason}: ${count}`).join('; ')}.</p>
          </details>
        </>}
    </section>}
    <DayFeedback initial={d.verdict} label="Note about these days"
      onSave={value => feedback.mutate({ outcome: d.outcome, split: d.split, feedback: value })}
      pending={feedback.isPending} error={feedback.isError} />
  </Panel>;
}

function DayGroup({ title, days }: { title: string; days: ContributingDay[] }) {
  const [shown, setShown] = useState(5);
  return <section aria-label={title}>
    <h3>{title} ({days.length})</h3>
    {days.slice(0, shown).map(day => <div key={day.day} className={styles.account}>
      {day.day} · score {day.value} · measured {day.splitValue}
      {day.entryIds.map(id => <Link key={id} to={`/journal?entry=${id}`}>Open check-in</Link>)}
    </div>)}
    {shown < days.length && <Button size="sm" onClick={() => setShown(shown + 5)}>Show more days</Button>}
  </section>;
}

function DayFeedback({ initial, onSave, pending, error, label }: {
  initial: PatternVerdict | null; onSave: (feedback: PatternVerdict) => void;
  pending: boolean; error: boolean; label: string;
}) {
  const [feedback, setFeedback] = useState<PatternVerdict>(initial ?? { verdict: null, note: null });
  return <div className={styles.feedback}>
    <ChoiceGroup label="Does this ring true?" tone="confirm" options={VERDICTS} value={feedback.verdict}
      clearable disabled={pending} onChange={value => {
        const next = { ...feedback, verdict: value }; setFeedback(next); onSave(next);
      }} />
    <label>{label}<textarea value={feedback.note ?? ''}
      onChange={event => setFeedback({ ...feedback, note: event.target.value })} /></label>
    <Button size="sm" disabled={pending} onClick={() => onSave(feedback)}>Save note</Button>
    {error && <p role="alert" className={styles.error}>Feedback not saved. Try again.</p>}
  </div>;
}

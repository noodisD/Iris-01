import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  useDayDifferenceDetail, useDayDifferences, useDayDifferenceVerdict, useDifferenceDetail,
  useDifferences, useDifferenceVerdict, usePatternVerdict,
} from '@/hooks/usePatterns';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { evidenceHref } from '@/lib/evidence';
import type {
  ContributingDay, DayDifference, DayDiagnostics, Difference, DiscoveryRange, Occasion,
  OutcomePair, PatternVerdict, PatternVerdictValue,
} from '@/types/api';
import { Badge, Button, ChoiceGroup, Page, Panel } from '@/ui';
import { DiscoveryStatusStrip } from './DiscoveryStatusStrip';
import { DiscoveryPeriod, InvalidDiscoveryPeriod, useDiscoveryPeriod } from './DiscoveryPeriod';
import styles from './InsightsScreen.module.css';

const VERDICTS: { value: PatternVerdictValue; label: string }[] = [
  { value: 'rings_true', label: 'Rings true' },
  { value: 'does_not', label: "Doesn't ring true" },
  { value: 'unsure', label: 'Unsure' },
];


export function InsightsScreen() {
  const [period, setPeriod] = useDiscoveryPeriod();
  if (!period) return <InvalidDiscoveryPeriod />;
  return <Page title="Insights" width="standard"
    description="Two recorded situations to compare, cautious co-label contrasts, and measured days. These are observations, not causes or advice.">
    <DiscoveryPeriod period={period} onChange={setPeriod} />
    <DiscoveryStatusStrip />
    <WritingSection period={period} />
    <DaySection period={period} />
  </Page>;
}

type WritingCard = { kind: 'co_label'; difference: Difference } | { kind: 'outcome_pair'; pair: OutcomePair };

function WritingSection({ period }: { period: DiscoveryRange }) {
  const { data, isPending, isError, refetch } = useDifferences(period);
  const [filter, setFilter] = useState<'current' | 'saved' | 'dismissed'>('current');
  const [showAll, setShowAll] = useState(false);
  const cards: WritingCard[] = [
    ...(data?.differences.map(difference => ({ kind: 'co_label' as const, difference })) ?? []),
    ...(data?.reflections.map(pair => ({ kind: 'outcome_pair' as const, pair })) ?? []),
  ];
  const visible = cards.filter(card => {
    const verdict = card.kind === 'co_label' ? card.difference.verdict?.verdict : card.pair.verdict?.verdict;
    const dismissed = card.kind === 'co_label' ? card.difference.dismissed : verdict === 'does_not';
    return filter === 'dismissed' ? dismissed : filter === 'saved' ? !dismissed && verdict != null : !dismissed;
  });
  const first: WritingCard[] = [];
  const remaining: WritingCard[] = [];
  const used = new Set<string>();
  visible.forEach(card => {
    const id = card.kind === 'co_label' ? card.difference.patternId : card.pair.patternId;
    if (first.length < 3 && !used.has(id)) { first.push(card); used.add(id); }
    else remaining.push(card);
  });
  return <section aria-label="Writing differences" className={styles.section}>
    <h2 className={styles.heading}>From your writing</h2>
    {isPending ? <LoadingState label="Comparing recorded situations…" />
      : isError || !data ? <ErrorState onRetry={() => refetch()} /> : <>
        <p className={styles.note}>{data.coverage.entryCount} contributing entries · recorded {data.coverage.recordedFrom ?? 'date unknown'} to {data.coverage.recordedTo ?? 'date unknown'}. Unwritten events are not counted as absences.</p>
        <div className={styles.meta}>
          {(['current', 'saved', 'dismissed'] as const).map(choice =>
            <Button key={choice} size="sm" onClick={() => { setFilter(choice); setShowAll(false); }}
              disabled={filter === choice}>{choice === 'current' ? 'Current' : choice === 'saved' ? 'Saved opinions' : 'Dismissed'}</Button>)}
        </div>
        {visible.length === 0 ? <EmptyState title="No writing comparisons in this view."
          body={data.coverage.entryCount === 0
            ? 'No source-backed accounts in this period. Review your Journal or read existing writing.'
            : 'The current accounts do not meet the conservative comparison rule, or there are no differently classified accounts from separate entries.'} />
          : <>
            {[...first, ...(showAll ? remaining : [])].map(card => card.kind === 'co_label'
              ? <CoLabelCard key={`co/${period}/${card.difference.patternId}/${card.difference.otherId}`}
                  d={card.difference} period={period} />
              : <PairCard key={`pair/${period}/${card.pair.patternId}`} pair={card.pair} period={period} />)}
            {remaining.length > 0 && <Button size="sm" onClick={() => setShowAll(!showAll)}>
              {showAll ? 'Show fewer' : `Show all comparisons (${remaining.length} more)`}
            </Button>}
          </>}
      </>}
  </section>;
}

function EvidenceAccount({ account }: { account: Occasion }) {
  return <div className={styles.account}>
    <span className={styles.note}>Recorded {account.recordedOn ?? 'date unknown'} · provisional {account.tone}</span>
    <p>{account.response}{account.outcome && <> → {account.outcome}</>}</p>
    {account.explanation && <blockquote>Your interpretation in the entry: {account.explanation}</blockquote>}
    {account.citations.map((citation, index) => <blockquote key={index}>
      {citation.text}{' '}
      {citation.sourceType === 'reflection' && <Link to={`/journal?entry=${citation.entryId}`}>Open entry</Link>}
    </blockquote>)}
  </div>;
}

function CoLabelCard({ d, period }: { d: Difference; period: DiscoveryRange }) {
  const feedback = useDifferenceVerdict();
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState<Record<string, number>>({
    betterWith: 5, betterWithout: 5, worseWith: 5, worseWithout: 5,
  });
  const detail = useDifferenceDetail(d.patternId, d.otherId, period, d.snapshot, open);
  const moreOnWorse = d.worseRate > d.betterRate;
  return <Panel as="article" aria-label={`${d.patternName} and ${d.otherName}`}>
    <p className={styles.sentence}>{d.otherName} was labelled more often among {d.patternName} accounts
      read as {moreOnWorse ? 'worse' : 'better'}.</p>
    <p className={styles.meta}>Read as worse: {d.worse}/{d.worseTotal} ({Math.round(d.worseRate * 100)}%).
      Read as better: {d.better}/{d.betterTotal} ({Math.round(d.betterRate * 100)}%).</p>
    <p className={styles.note}>Exploratory · {d.coverage.range} · {d.coverage.entryCount} entries.
      Small samples; not labelled with {d.otherName} is not evidence that it was absent.</p>
    <div className={styles.meta}>
      <Link to={`/patterns/${encodeURIComponent(d.patternId)}?range=${period}`}>{d.patternName}</Link>
      <Link to={`/patterns/${encodeURIComponent(d.otherId)}?range=${period}`}>{d.otherName}</Link>
      <Link to={evidenceHref({ kind: 'co_label', patternId: d.patternId,
        otherId: d.otherId, range: period, snapshot: d.snapshot })}>Explore with Iris</Link>
      <Button size="sm" onClick={() => setOpen(!open)}>{open ? 'Hide evidence' : 'See the evidence'}</Button>
    </div>
    {open && <section aria-label="Co-label evidence" className={styles.evidence}>
      {detail.isPending ? <LoadingState label="Opening the contributing accounts…" />
        : detail.isError || !detail.data ? <ErrorState onRetry={() => detail.refetch()} />
        : <>
          {(Object.keys(detail.data.groups) as (keyof typeof detail.data.groups)[]).map(group => {
            const accounts = detail.data.groups[group];
            return <section key={group} aria-label={group}>
              <h3>{group.replace('With', ' · labelled with').replace('Without', ' · not labelled with')} ({accounts.length})</h3>
              {accounts.slice(0, shown[group]).map(account => <EvidenceAccount key={account.id} account={account} />)}
              {accounts.length > shown[group] && <Button size="sm"
                onClick={() => setShown(current => ({ ...current, [group]: current[group] + 5 }))}>Show more</Button>}
            </section>;
          })}
          <p className={styles.note}>{detail.data.mixedExcluded} mixed accounts excluded from both denominators.</p>
        </>}
    </section>}
    <DifferenceFeedback initial={d.verdict} label="Note about this comparison"
      onSave={value => feedback.mutate({ patternId: d.patternId, otherId: d.otherId, feedback: value })}
      pending={feedback.isPending} error={feedback.isError} />
  </Panel>;
}

function PairCard({ pair, period }: { pair: OutcomePair; period: DiscoveryRange }) {
  const feedback = usePatternVerdict(pair.patternId);
  return <Panel as="article" aria-label={`Two recorded situations: ${pair.patternName}`}>
    <Badge>Two recorded situations to compare</Badge>
    <h3>{pair.patternName}</h3>
    <div className={styles.pair}>
      <section aria-label="Read as better"><EvidenceAccount account={pair.better} /></section>
      <section aria-label="Read as worse"><EvidenceAccount account={pair.worse} /></section>
    </div>
    <p className={styles.sentence}>What do you make of the difference between these situations?</p>
    <p className={styles.note}>{pair.betterTotal} better · {pair.worseTotal} worse · {pair.mixedTotal} mixed recorded accounts.
      The response did not necessarily cause the outcome.</p>
    <div className={styles.meta}>
      <Link to={`/patterns/${encodeURIComponent(pair.patternId)}?range=${period}`}>See the evidence</Link>
      <Link to={evidenceHref({ kind: 'outcome_pair', patternId: pair.patternId,
        range: period, snapshot: pair.snapshot })}>Explore with Iris</Link>
    </div>
    <DifferenceFeedback initial={pair.verdict} label="Note about this pattern"
      onSave={value => feedback.mutate(value)} pending={feedback.isPending} error={feedback.isError} />
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
  return <section aria-label="Days compared" className={styles.section}>
    <h2 className={styles.heading}>Days compared</h2>
    <p className={styles.note}>Explicit check-ins against confirmed phone measurements; neither is a census of life.</p>
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
    <DifferenceFeedback initial={d.verdict} label="Note about these days"
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

function DifferenceFeedback({ initial, onSave, pending, error, label }: {
  initial: PatternVerdict | null; onSave: (feedback: PatternVerdict) => void;
  pending: boolean; error: boolean; label: string;
}) {
  const [feedback, setFeedback] = useState<PatternVerdict>(initial ?? { verdict: null, note: null });
  return <div className={styles.feedback}>
    <ChoiceGroup label="Does this ring true?" tone="confirm" options={VERDICTS} value={feedback.verdict}
      clearable disabled={pending} onChange={value => {
        const next = { ...feedback, verdict: value };
        setFeedback(next);
        onSave(next);
      }} />
    <label>{label}
      <textarea value={feedback.note ?? ''} onChange={event => setFeedback({ ...feedback, note: event.target.value })} />
    </label>
    <Button size="sm" disabled={pending} onClick={() => onSave(feedback)}>Save note</Button>
    {error && <p role="alert" className={styles.error}>Feedback not saved. Try again.</p>}
  </div>;
}

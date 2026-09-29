import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useOccasionVerdict, usePattern, usePatterns, usePatternVerdict } from '@/hooks/usePatterns';
import { LoadingState, ErrorState } from '@/components/states';
import { formatEventDate } from '@/lib/dates';
import { evidenceHref } from '@/lib/evidence';
import type { DiscoveryRange, Occasion, OccasionVerdictValue, PatternDetail, PatternSummary, PatternVerdictValue } from '@/types/api';
import { Button, ChoiceGroup, Panel } from '@/ui';
import { DiscoveryStatusStrip } from './DiscoveryStatusStrip';
import { DiscoveryPeriod, InvalidDiscoveryPeriod, useDiscoveryPeriod } from './DiscoveryPeriod';
import styles from './PatternsScreen.module.css';

/**
 * Discovery: general patterns from a library, and the occasions in your own
 * writing that are instances of them.
 *
 * For each pattern the occasions are split by how they went, with what else was
 * true on each side. A difference between the sides is shown as a difference,
 * never as a cause or as advice: what it means is yours to say. So are the two
 * verdicts here — whether an occasion really belongs to the pattern, and whether
 * the pattern rings true at all. Saying "not this" removes an occasion from the
 * counts without deleting it.
 */

const PATTERN_VERDICTS: { value: PatternVerdictValue; label: string }[] = [
  { value: 'rings_true', label: 'Rings true' },
  { value: 'does_not', label: "Doesn't ring true" },
  { value: 'unsure', label: 'Unsure' },
];
const OCCASION_VERDICTS: { value: OccasionVerdictValue; label: string }[] = [
  { value: 'yes', label: 'This one' },
  { value: 'no', label: 'Not this' },
  { value: 'unsure', label: 'Unsure' },
];

function accountCount(p: PatternSummary): string {
  return `${p.occasions} ${p.occasions === 1 ? 'account' : 'accounts'} across ${p.entryCount} ${p.entryCount === 1 ? 'entry' : 'entries'}`;
}

function discussionLink(p: PatternSummary, period: DiscoveryRange): string {
  return evidenceHref({ kind: 'pattern', patternId: p.id, range: period, snapshot: p.snapshot });
}

function PatternPreview({ pattern: p, period }: { pattern: PatternSummary; period: DiscoveryRange }) {
  return <Panel as="article" className={styles.preview}>
    <span className={styles.when}>{p.occasions === 1 ? 'One recorded entry · possible lens, not recurrence' : accountCount(p)}
      {p.recordedFrom && ` · recorded ${p.recordedFrom}${p.recordedTo !== p.recordedFrom ? `–${p.recordedTo}` : ''}`}
      {p.undatedAccountCount > 0 && ` · ${p.undatedAccountCount} undated`}</span>
    {p.examples.map(example => <div key={example.id} className={styles.excerpt}>
      <p className={styles.response}>{example.response}</p>
      {example.outcome && <p className={styles.outcome}>Then: {example.outcome}</p>}
      <span className={styles.when}>Recorded {example.recordedOn ?? 'date unknown'} · provisionally read as {example.tone}</span>
    </div>)}
    <h3 className={styles.previewName}>{p.name}</h3>
    <p className={styles.noteText}>A library lens for these recorded accounts, not a claim about how often this happens in life.</p>
    <div className={styles.actions}>
      <Link to={`/patterns/${encodeURIComponent(p.id)}?range=${period}`}>See examples</Link>
      <Link to={discussionLink(p, period)}>Explore with Iris</Link>
    </div>
  </Panel>;
}

export function PatternsScreen() {
  const [period, setPeriod] = useDiscoveryPeriod();
  if (!period) return <InvalidDiscoveryPeriod />;
  return <PatternsInPeriod period={period} onPeriodChange={setPeriod} />;
}

function PatternsInPeriod({ period, onPeriodChange }: {
  period: DiscoveryRange; onPeriodChange: (period: DiscoveryRange) => void;
}) {
  const { id } = useParams<{ id: string }>();
  const { data, isPending, isError, refetch } = usePatterns(period);
  const [showDismissed, setShowDismissed] = useState(false);
  if (isPending) return <LoadingState label="Iris is opening the library…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  const found = data.patterns.filter(p => p.occasions > 0 && p.verdict?.verdict !== 'does_not');
  const dismissed = data.patterns.filter(p => p.verdict?.verdict === 'does_not' || (p.occasions === 0 && p.rejected > 0));
  const unfound = data.patterns.length - found.length - dismissed.length;
  if (id) return <div className={styles.page}><PatternView id={id} period={period} /></div>;
  return <main className={styles.page}>
    <h1 className={styles.listTitle}>Patterns in your writing</h1>
    <DiscoveryPeriod period={period} onChange={onPeriodChange} />
    <DiscoveryStatusStrip />
    {found.length ? <>
      <section aria-label="Worth looking at">
        <h2 className={styles.sideTitle}>Worth looking at</h2>
        <div className={styles.previewList}>{found.slice(0, 3).map(p =>
          <PatternPreview key={p.id} pattern={p} period={period} />)}</div>
      </section>
      {found.length > 3 && <section aria-label="All found situations">
        <h2 className={styles.sideTitle}>All found situations</h2>
        <div className={styles.previewList}>{found.slice(3).map(p =>
          <PatternPreview key={p.id} pattern={p} period={period} />)}</div>
      </section>}
    </> : <p className={styles.none}>
      {period !== 'all' ? <>No accounts in this recorded period. <Button size="sm" onClick={() => onPeriodChange('all')}>All available writing</Button></>
        : <>No source-backed accounts found yet. <Link to="/journal">Open Journal</Link> to review your writing.</>}
    </p>}
    {dismissed.length > 0 && <section>
      <Button size="sm" onClick={() => setShowDismissed(!showDismissed)}>
        {showDismissed ? 'Hide dismissed' : `Dismissed (${dismissed.length})`}
      </Button>
      {showDismissed && <ul className={styles.items}>{dismissed.map(p => <li key={p.id}>
        <Link to={`/patterns/${encodeURIComponent(p.id)}?range=${period}`} className={styles.item}>
          {p.name} · {p.rejected} rejected {p.rejected === 1 ? 'account' : 'accounts'} · review or restore
        </Link>
      </li>)}</ul>}
    </section>}
    {unfound > 0 && <p className={styles.unfound}>{unfound} more library lenses not found in this writing</p>}
  </main>;
}

function PatternView({ id, period }: { id: string; period: DiscoveryRange }) {
  const { data, isPending, isError, refetch } = usePattern(id, period);
  if (isPending) return <LoadingState label="Iris is gathering the occasions…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;
  const { pattern: p } = data;

  const counted = data.occasions.filter(o => o.ownerVerdict !== 'no');
  const side = (tone: Occasion['tone']) => counted.filter(o => o.tone === tone);
  const rejected = data.occasions.filter(o => o.ownerVerdict === 'no');
  const labelledBy = [...new Set(data.occasions.map(o => o.labelledBy).filter(Boolean))];

  return (
    <article className={styles.pattern} aria-label={p.name}>
      <Link to={`/patterns?range=${period}`} className={styles.back}>← All patterns</Link>
      <h1 className={styles.patternName}>{p.name}</h1>
      <p className={styles.when}>{data.coverage.accountCount} recorded accounts across {data.coverage.entryCount} entries
        {data.coverage.undatedAccountCount > 0 && ` · ${data.coverage.undatedAccountCount} undated`}</p>
      <div className={styles.sides}>
        <Side title="Read as better" occasions={side('better')} patternId={p.id} />
        <Side title="Read as worse" occasions={side('worse')} patternId={p.id} />
      </div>
      {side('better').length === 0 || side('worse').length === 0
        ? <p className={styles.none}>No differently classified account in this reading.</p> : null}
      {side('mixed').length > 0 && <Side title="Mixed" occasions={side('mixed')} patternId={p.id} />}
      {rejected.length > 0 && <div className={styles.rejected}>
        <Side title="You said: not this pattern" occasions={rejected} patternId={p.id} />
      </div>}
      {data.occasions.length === 0 && <p className={styles.none}>
        No source-backed example in this reading. This is only a general library lens.
        {period !== 'all' && <> <Link to={`/patterns/${encodeURIComponent(id)}?range=all`}>All available writing</Link></>}
      </p>}
      <h2 className={styles.sideTitle}>A question to consider</h2>
      <p className={styles.statement}>{p.question}</p>
      <Distinctive data={data} period={period} />
      <section className={styles.patternHead}>
        <h2 className={styles.sideTitle}>Why this lens?</h2>
        <p className={styles.statement}>{p.statement}</p>
        {p.holdsWhen.length > 0 && <p>It may fit when: {p.holdsWhen.join('; ')}</p>}
        {p.notWhen.length > 0 && <p>It may not fit when: {p.notWhen.join('; ')}</p>}
        {p.basis && <p className={styles.basis}>General research basis: {p.basis}</p>}
        {p.evidence && <p className={styles.provenance}>Library evidence: {p.evidence}</p>}
        {p.source && <a href={p.source} target="_blank" rel="noreferrer">Library source</a>}
      </section>
      <PatternFeedback key={`${id}/${period}`} id={id} initial={data.verdict} />
      {labelledBy.length > 0 && <p className={styles.labelled}>Provisional library matching by {labelledBy.join(', ')}</p>}
    </article>
  );
}

function PatternFeedback({ id, initial }: { id: string; initial: PatternDetail['verdict'] }) {
  const verdict = usePatternVerdict(id);
  const [feedback, setFeedback] = useState(initial ?? { verdict: null, note: null });
  return <div className={styles.verdict}>
    <span className={styles.verdictLabel}>Does it ring true?</span>
    <ChoiceGroup label="Does it ring true?" tone="confirm" options={PATTERN_VERDICTS} value={feedback.verdict}
      clearable disabled={verdict.isPending} onChange={value => {
        const next = { ...feedback, verdict: value };
        setFeedback(next);
        verdict.mutate(next);
      }} />
    <label>Note about this pattern
      <textarea value={feedback.note ?? ''} onChange={event => setFeedback({ ...feedback, note: event.target.value })} />
    </label>
    <Button size="sm" disabled={verdict.isPending} onClick={() => verdict.mutate(feedback)}>Save note</Button>
    {verdict.isError && <p role="alert">Opinion not saved. Try again.</p>}
  </div>;
}

function Side({ title, occasions, patternId }: { title: string; occasions: Occasion[]; patternId: string }) {
  return (
    <section aria-label={title.toLowerCase()} className={styles.side}>
      <h3 className={styles.sideTitle}>{title} ({occasions.length})</h3>
      {occasions.map(o => <OccasionCard key={`${patternId}/${o.id}`} occasion={o} patternId={patternId} />)}
    </section>
  );
}

function OccasionCard({ occasion: o, patternId }: { occasion: Occasion; patternId: string }) {
  const verdict = useOccasionVerdict(patternId);
  const [feedback, setFeedback] = useState({
    verdict: o.ownerVerdict, note: o.verdictNote ?? '', ownerTone: o.ownerTone,
  });
  return (
    <Panel as="article" aria-label={`occasion: ${o.situation}`} tone={o.ownerVerdict === 'yes' ? 'confirmed' : undefined}>
      <span className={styles.when}>{o.recordedOn ? `Recorded ${formatEventDate(o.recordedOn)}` : 'Recorded date unknown'}</span>
      <p className={styles.situation}>{o.situation}</p>
      <p className={styles.response}>{o.response}</p>
      {o.outcome && <p className={styles.outcome}>Then: {o.outcome}</p>}
      {o.explanation && <blockquote className={styles.quote}>Your interpretation in the entry: {o.explanation}</blockquote>}
      {o.citations.map((c, i) => (
        <blockquote key={i} className={styles.quote}>
          {c.text}{' '}
          {c.sourceType === 'reflection' && <Link to={`/journal?entry=${c.entryId}`}>open entry</Link>}
        </blockquote>
      ))}
      <ChoiceGroup label="Is this an occasion of the pattern?" options={OCCASION_VERDICTS} value={feedback.verdict}
        clearable disabled={verdict.isPending}
        onChange={value => {
          const next = { ...feedback, verdict: value };
          setFeedback(next);
          verdict.mutate({ occasionId: o.id, feedback: next });
        }} />
      <label>How would you read this outcome?
        <select value={feedback.ownerTone ?? ''} onChange={event => {
          const ownerTone = event.target.value === '' ? null : event.target.value as Occasion['tone'];
          const next = { ...feedback, ownerTone };
          setFeedback(next);
          verdict.mutate({ occasionId: o.id, feedback: next });
        }}>
          <option value="">Keep provisional classification ({o.suggestedTone})</option>
          <option value="better">Better</option><option value="worse">Worse</option><option value="mixed">Mixed</option>
        </select>
      </label>
      <label>Note about this account
        <textarea value={feedback.note} onChange={event => setFeedback({ ...feedback, note: event.target.value })} />
      </label>
      <Button size="sm" disabled={verdict.isPending}
        onClick={() => verdict.mutate({ occasionId: o.id, feedback })}>Save note</Button>
      {verdict.isError && <p role="alert">Account feedback not saved. Try again.</p>}
    </Panel>
  );
}

function Distinctive({ data, period }: { data: PatternDetail; period: DiscoveryRange }) {
  if (data.distinctive.length === 0) return null;
  return (
    <section aria-label="what else differed" className={styles.differed}>
      <h3 className={styles.sideTitle}>What else differed between the sides</h3>
      <ul>
        {data.distinctive.map(d => (
          <li key={d.patternId}>
            <Link to={`/patterns/${encodeURIComponent(d.patternId)}?range=${period}`}>{d.name}</Link>
            <span className={styles.counts}>worse {d.worse}/{d.worseTotal} ({Math.round(d.worseRate * 100)}%) ·
              better {d.better}/{d.betterTotal} ({Math.round(d.betterRate * 100)}%)</span>
          </li>
        ))}
      </ul>
      <p className={styles.noteText}>Only groups of at least three accounts with both a two-account and 25-point rate gap.
        Provisional co-labels in recorded writing; not causes or advice.</p>
    </section>
  );
}

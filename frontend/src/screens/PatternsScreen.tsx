import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAccountVerdict, useDiscoveryStatus, usePattern, usePatterns, usePatternVerdict } from '@/hooks/usePatterns';
import { LoadingState, ErrorState } from '@/components/states';
import { evidenceHref } from '@/lib/evidence';
import type { AccountCitation, AccountVerdictValue, DiscoveryRange, EventGroup, FeedbackRequest,
  GroundedClause, Membership, PatternDetail, PatternVerdictValue, PersonalAccount, PersonalPattern,
  ProcessLens, SavedFeedback } from '@/types/api';
import { Button, ChoiceGroup, Panel } from '@/ui';
import { DiscoveryStatusStrip } from './DiscoveryStatusStrip';
import { DiscoveryPeriod, InvalidDiscoveryPeriod, useDiscoveryPeriod } from './DiscoveryPeriod';
import styles from './PatternsScreen.module.css';

const VERDICTS: { value: PatternVerdictValue; label: string }[] = [
  { value: 'rings_true', label: 'Rings true' },
  { value: 'does_not', label: "Doesn't ring true" },
  { value: 'unsure', label: 'Unsure' },
];
const ACCOUNT_VERDICTS: { value: AccountVerdictValue; label: string }[] = [
  { value: 'yes', label: 'This fits' }, { value: 'no', label: 'Not this' }, { value: 'unsure', label: 'Unsure' },
];

export function CitationLink({ citation }: { citation: AccountCitation }) {
  return citation.sourceType === 'reflection'
    ? <Link to={`/journal?entry=${encodeURIComponent(String(citation.entryId))}`}>Open entry</Link> : null;
}

export function AccountEvidence({ account }: { account: PersonalAccount }) {
  return <div className={styles.account}>
    <p className={styles.when}>Recorded {account.recordedOn ?? 'date unknown'} · {account.recordKind.replace('_', ' ')}
      {account.actor !== 'self' && ` · ${account.actor} actor`}</p>
    {account.situation && <p>Situation: {account.situation}</p>}
    {account.response && <p>Response: {account.response}</p>}
    {account.selfReport && <p>You described: {account.selfReport}</p>}
    {account.feeling && <p>Feeling you recorded: {account.feeling}</p>}
    {account.concern && <p>Concern you recorded: {account.concern}</p>}
    {account.demand && <p>Demand you recorded: {account.demand}</p>}
    {account.information && <p>Information you recorded: {account.information}</p>}
    {account.immediateOutcome && <p>Immediate outcome: {account.immediateOutcome}</p>}
    {account.laterOutcome && <p>Later outcome: {account.laterOutcome}</p>}
    {account.explanation && <p>You wrote: {account.explanation}</p>}
    {account.citations.map((citation, index) => <blockquote key={index} className={styles.quote}>
      {citation.text} <CitationLink citation={citation} />
    </blockquote>)}
  </div>;
}

export function SourcedClause({ clause, accounts }: {
  clause: GroundedClause; accounts: Record<string, PersonalAccount>;
}) {
  const citations = clause.refs.map(ref => accounts[ref.accountId]?.citations[ref.citationIndex])
    .filter((citation): citation is AccountCitation => Boolean(citation));
  return <div><p>{clause.text}</p>
    {citations.length > 0 && <div className={styles.sources}>Source: {citations.map((citation, index) =>
      <span key={`${citation.entryId}/${index}`}><CitationLink citation={citation} />{index < citations.length - 1 && ' · '}</span>)}</div>}
  </div>;
}

export function VerdictEditor({ initial, range, snapshot, onSave, pending, error, label, draftKey }: {
  initial: SavedFeedback<PatternVerdictValue> | null; range: DiscoveryRange; snapshot: string;
  onSave: (value: FeedbackRequest<PatternVerdictValue>) => void;
  pending: boolean; error: boolean; label: string; draftKey: string;
}) {
  const [feedback, setFeedback] = useState({ verdict: initial?.verdict ?? null as PatternVerdictValue | null,
    note: sessionStorage.getItem(draftKey) ?? initial?.note ?? null as string | null });
  const save = (next: typeof feedback) => onSave({ ...next, range, snapshot });
  return <div className={styles.feedback}>
    {initial?.needsReview && <p role="status">Your saved opinion needs review because the evidence changed.</p>}
    <ChoiceGroup label="Does this ring true?" tone="confirm" options={VERDICTS} value={feedback.verdict}
      clearable disabled={pending} onChange={value => {
        const next = { ...feedback, verdict: value }; setFeedback(next); save(next);
      }} />
    <label>{label}<textarea maxLength={1000} value={feedback.note ?? ''}
      onChange={event => {
        const note = event.target.value;
        sessionStorage.setItem(draftKey, note);
        setFeedback({ ...feedback, note });
      }} /></label>
    <Button size="sm" disabled={pending} onClick={() => save(feedback)}>Save note</Button>
    {initial?.needsReview && feedback.verdict && <Button size="sm" disabled={pending}
      onClick={() => save(feedback)}>Confirm this opinion on current evidence</Button>}
    {error && <p role="alert">Opinion not saved. Review current evidence and try again.</p>}
  </div>;
}

function PatternCard({ pattern: p, range }: { pattern: PersonalPattern; range: DiscoveryRange }) {
  return <Panel as="article" className={styles.preview}>
    <h3 className={styles.previewName}>{p.title}</h3>
    <p>{p.context.text} → {p.response.text}</p>
    <p className={styles.when}>{p.evidenceState === 'owner_described' ? 'You described this' : p.evidenceState} ·
      {' '}at least {p.independentGroupCount} distinct occasions identified / {p.accountCount} accounts
      {p.recordedFrom && ` · recorded ${p.recordedFrom}${p.recordedTo !== p.recordedFrom ? `–${p.recordedTo}` : ''}`}
      {p.undatedAccountCount > 0 && ` · ${p.undatedAccountCount} undated`}</p>
    {p.example && <blockquote className={styles.quote}>{p.example.citation.text}{' '}
      <CitationLink citation={p.example.citation} /></blockquote>}
    {p.feedback?.needsReview && <p>Saved opinion needs review</p>}
    <div className={styles.actions}>
      <Link to={`/patterns/${encodeURIComponent(p.id)}?range=${range}`}>See evidence</Link>
      <Link to={evidenceHref({ kind: 'dynamic', dynamicId: p.id, range, snapshot: p.snapshot })}>Explore with Iris</Link>
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
  if (id) return <main className={styles.page}><PatternView id={id} period={period} onPeriodChange={onPeriodChange} /></main>;
  return <main className={styles.page}>
    <h1 className={styles.listTitle}>Patterns in your writing</h1>
    <DiscoveryPeriod period={period} onChange={onPeriodChange} />
    <DiscoveryStatusStrip />
    {isPending ? <LoadingState label="Opening personal patterns…" />
      : isError || !data ? <ErrorState onRetry={() => refetch()} />
      : data.status.stage !== 'ready' ? <p role="status">Personal discovery is not current yet. These are not empty findings.</p>
      : data.patterns.length ? <>
        {data.patterns.filter(p => p.evidenceState !== 'owner_described').map(p =>
          <PatternCard key={p.id} pattern={p} range={period} />)}
        {data.patterns.some(p => p.evidenceState === 'owner_described') && <section>
          <h2 className={styles.sideTitle}>You described this</h2>
          {data.patterns.filter(p => p.evidenceState === 'owner_described').map(p =>
            <PatternCard key={p.id} pattern={p} range={period} />)}
        </section>}
      </> : <p className={styles.none}>No checked recurring dynamics found in this recorded writing.
        {period !== 'all' && <> <Button size="sm" onClick={() => onPeriodChange('all')}>All available writing</Button></>}
      </p>}
  </main>;
}

function AccountReview({ account, membership, range, snapshot, dynamicId }: {
  account: PersonalAccount; membership: Membership | undefined; range: DiscoveryRange;
  snapshot: string; dynamicId: string;
}) {
  const correction = useAccountVerdict(dynamicId);
  const draftKey = `iris:account-note:${dynamicId}/${account.id}/${range}`;
  const [feedback, setFeedback] = useState({ verdict: membership?.ownerVerdict ?? null as AccountVerdictValue | null,
    note: sessionStorage.getItem(draftKey) ?? membership?.verdictNote ?? null as string | null });
  const save = (next: typeof feedback) => correction.mutate(
    { accountId: account.id, feedback: { ...next, range, snapshot } },
    { onSuccess: () => sessionStorage.removeItem(draftKey) },
  );
  return <Panel as="article" className={styles.account}>
    {membership && <p className={styles.when}>Checked role: {membership.role.replace('_', ' ')} ·
      {' '}{membership.contextDecision} context · {membership.responseDecision} response ·
      {' '}{membership.relationDecision} relation
      {membership.excluded && ' · excluded from counts by your correction'}</p>}
    <AccountEvidence account={account} />
    {membership && <div className={styles.feedback}>
      <ChoiceGroup label="Is this account classified here?" options={ACCOUNT_VERDICTS} value={feedback.verdict}
        clearable disabled={correction.isPending} onChange={value =>
          setFeedback({ ...feedback, verdict: value })} />
      <label>Note about this account<textarea maxLength={1000} value={feedback.note ?? ''}
        onChange={event => {
          const note = event.target.value;
          sessionStorage.setItem(draftKey, note);
          setFeedback({ ...feedback, note });
        }} /></label>
      <Button size="sm" disabled={correction.isPending} onClick={() => save(feedback)}>Save correction</Button>
      {correction.isError && <p role="alert">Account correction not saved. Review current evidence and try again.</p>}
    </div>}
  </Panel>;
}

function EvidenceGroups({ data, period }: { data: PatternDetail; period: DiscoveryRange }) {
  const id = data.pattern.id;
  const rows = data.memberships[id] ?? [];
  const groups = data.groups[id] ?? [];
  const rejected = rows.filter(row => row.excluded || row.ownerVerdict === 'no');
  const shown = new Set<string>();
  return <>
    {groups.map((group: EventGroup) => {
      const accounts = group.accountIds.filter(accountId => {
        const row = rows.find(item => item.accountId === accountId);
        if (!row || row.excluded || !data.accounts[accountId]) return false;
        shown.add(accountId); return true;
      });
      if (accounts.length === 0) return null;
      return <section key={group.id} className={styles.group} aria-label={`Event group ${group.id}`}>
        <h3 className={styles.sideTitle}>{group.role.replace('_', ' ')} · {accounts.length} accounts
          {group.independentlyCountable && ' · independently identified'}
          {group.independenceUncertain && ' · independence uncertain'}</h3>
        {accounts.map(accountId => <AccountReview key={`${accountId}/${data.snapshot}`} dynamicId={id}
          account={data.accounts[accountId]} membership={rows.find(row => row.accountId === accountId)}
          range={period} snapshot={data.snapshot} />)}
      </section>;
    })}
    {rows.filter(row => !shown.has(row.accountId) && !row.excluded && data.accounts[row.accountId]).length > 0 &&
      <section aria-label="Other checked accounts"><h3 className={styles.sideTitle}>Other checked accounts</h3>
        {rows.filter(row => !shown.has(row.accountId) && !row.excluded && data.accounts[row.accountId]).map(row =>
          <AccountReview key={`${row.accountId}/${data.snapshot}`} dynamicId={id} account={data.accounts[row.accountId]}
            membership={row} range={period} snapshot={data.snapshot} />)}
      </section>}
    {rejected.length > 0 && <section aria-label="Your corrections">
      <h3 className={styles.sideTitle}>Your corrections</h3>
      {rejected.filter(row => data.accounts[row.accountId]).map(row =>
        <AccountReview key={`${row.accountId}/${data.snapshot}`} dynamicId={id} account={data.accounts[row.accountId]}
          membership={row} range={period} snapshot={data.snapshot} />)}
    </section>}
  </>;
}

function PatternView({ id, period, onPeriodChange }: {
  id: string; period: DiscoveryRange; onPeriodChange: (range: DiscoveryRange) => void;
}) {
  const { data, isPending, isError, refetch } = usePattern(id, period);
  const status = useDiscoveryStatus();
  const feedback = usePatternVerdict(id);
  if (isPending) return <LoadingState label="Opening checked evidence…" />;
  if (isError && status.data && status.data.stage !== 'ready') return <>
    <Link to={`/patterns?range=${period}`}>← All patterns</Link>
    <DiscoveryStatusStrip />
    <p role="status">The corrected evidence is being rechecked. This pattern will return if it still qualifies.</p>
  </>;
  if (isError || !data) return <><Link to={`/patterns?range=${period}`}>← All patterns</Link>
    <ErrorState onRetry={() => refetch()} /></>;
  const p = data.pattern;
  return <article className={styles.pattern} aria-label={p.title}>
    <Link to={`/patterns?range=${period}`} className={styles.back}>← All patterns</Link>
    <DiscoveryPeriod period={period} onChange={onPeriodChange} />
    <DiscoveryStatusStrip />
    <h1 className={styles.patternName}>{p.title}</h1>
    <p className={styles.when}>{p.evidenceState === 'owner_described' ? 'You described this' : p.evidenceState} ·
      {' '}at least {p.independentGroupCount} distinct occasions identified / {p.accountCount} accounts ·
      {' '}{p.entryCount} entries. Recording dates do not establish when events happened.</p>
    <section><h2 className={styles.sideTitle}>What you wrote</h2>
      <SourcedClause clause={p.context} accounts={data.accounts} />
      <SourcedClause clause={p.response} accounts={data.accounts} />
      {p.ownerMeanings.map((meaning, index) => <div key={index}>You wrote:
        <SourcedClause clause={meaning} accounts={data.accounts} /></div>)}
    </section>
    <section><h2 className={styles.sideTitle}>What seems to recur</h2>
      <p>{p.evidenceState === 'owner_described' ? 'An explicit owner description, not counted recurrence.'
        : `At least ${p.independentGroupCount} distinct occasions identified.`}</p>
      <p>{p.exceptionCount} recorded exceptions · {p.unknownAccountCount} accounts remain unclear.</p>
      <div><strong>Immediate return:</strong> {p.immediateReturn
        ? <SourcedClause clause={p.immediateReturn} accounts={data.accounts} /> : 'Not recorded'}</div>
      <div><strong>Later cost:</strong> {p.laterCost
        ? <SourcedClause clause={p.laterCost} accounts={data.accounts} /> : 'Not recorded'}</div>
    </section>
    <section><h2 className={styles.sideTitle}>One possible explanation</h2>
      {p.possibleMeaning ? <><p>{p.possibleMeaning.text}</p>
        {p.possibleMeaning.premises.map((premise, index) =>
          <SourcedClause key={index} clause={premise} accounts={data.accounts} />)}</> : <p>Not recorded sufficiently to propose one.</p>}
    </section>
    <section><h2 className={styles.sideTitle}>Another possibility</h2>
      {p.alternative ? <><p>{p.alternative.text}</p>
        {p.alternative.premises.map((premise, index) =>
          <SourcedClause key={index} clause={premise} accounts={data.accounts} />)}</> : <p>Not recorded sufficiently to propose one.</p>}
    </section>
    <section><h2 className={styles.sideTitle}>When it was different</h2>
      <p>{p.exceptionGroupIds.length ? `${p.exceptionGroupIds.length} checked exception groups.`
        : 'No exception recorded in the checked writing.'}</p>
      {p.responseElsewhereGroupIds.length > 0 && <p>{p.responseElsewhereGroupIds.length} response-elsewhere groups.</p>}
    </section>
    <section><h2 className={styles.sideTitle}>What is not recorded</h2>
      <p>{p.unknownAccountCount} unclear accounts · {data.checks.omittedAccounts} omitted accounts ·
        {' '}{data.checks.omittedFields} unsupported fields omitted ·
        {' '}{data.checks.unclear} unclear checks. {p.openQuestion}</p>
    </section>
    {p.lensMatches.length > 0 && <details><summary>A way to understand this (general library lenses)</summary>
      {p.lensMatches.map(match => {
        const lens: ProcessLens | undefined = data.lenses.find(row => row.id === match.lensId);
        return lens && <section key={match.lensId}>
          <h3>{lens.name}</h3><p>{lens.sequence}</p><p>Possible function: {lens.possibleFunction}</p>
          <p>Another account: {lens.alternative}</p><p>May not fit when: {lens.notWhen}</p>
          <p>{lens.question}</p>
        </section>;
      })}
    </details>}
    <p><Link to={evidenceHref({ kind: 'dynamic', dynamicId: id, range: period, snapshot: p.snapshot })}>Explore with Iris</Link></p>
    <VerdictEditor key={`${id}/${period}/${data.snapshot}`} draftKey={`iris:pattern-note:${id}/${period}`}
      initial={p.feedback} range={period} snapshot={data.snapshot}
      label="Note about this pattern" pending={feedback.isPending} error={feedback.isError}
      onSave={value => feedback.mutate(value, {
        onSuccess: () => sessionStorage.removeItem(`iris:pattern-note:${id}/${period}`),
      })} />
    <details open><summary>All checked accounts and event groups</summary>
      <EvidenceGroups data={data} period={period} />
    </details>
  </article>;
}

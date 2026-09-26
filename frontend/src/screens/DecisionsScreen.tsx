import React from 'react';
import { useCreateDecision, useDecisions, useRecordOutcome } from '@/hooks/useDecisions';
import { LoadingState, ErrorState } from '@/components/states';
import { formatEventDate } from '@/lib/dates';
import type {
  Decision, DecisionCreate, Feeling, FollowedPlan, LastDays, Pressure, Reversible, Stake, WouldRepeat,
} from '@/types/api';
import { Button, Page } from '@/ui';
import styles from './DecisionsScreen.module.css';

/**
 * A decision journal, filled in at the moment a decision is made — any kind:
 * a job, a move, a purchase, a conversation, a plan.
 *
 * Looking back through the writing could not say when a decision grew too
 * large, because the facts that would say so were almost never written down:
 * what was at stake and whether it could be undone, what the days before held,
 * what was pushing, how you had slept and felt. These are those facts, asked at
 * the time. Only the first is required: a form that demands everything in the
 * moment gets skipped, and a skipped entry helps less than a partial one.
 */

type Option<T> = { value: T; label: string };

const STAKES: Option<Stake>[] = [
  { value: 'little', label: 'little' },
  { value: 'fair', label: 'a fair amount' },
  { value: 'a_lot', label: 'a lot' },
  { value: 'beyond_means', label: 'more than I can afford to lose' },
];
const REVERSIBLE: Option<Reversible>[] = [
  { value: 'easily', label: 'easily' },
  { value: 'at_a_cost', label: 'at a cost' },
  { value: 'not_at_all', label: 'not at all' },
];
const LAST_DAYS: Option<LastDays>[] = [
  { value: 'setback', label: 'a setback' },
  { value: 'success', label: 'a success' },
  { value: 'neither', label: 'neither' },
];
const PRESSURES: Option<Pressure>[] = [
  { value: 'deadline', label: 'a deadline' },
  { value: 'money', label: 'money' },
  { value: 'people', label: 'other people' },
  { value: 'urge', label: 'a strong urge' },
];
const FEELINGS: Option<Feeling>[] = [
  { value: 'calm', label: 'calm' },
  { value: 'excited', label: 'excited' },
  { value: 'anxious', label: 'anxious' },
  { value: 'frustrated', label: 'frustrated' },
];
const FOLLOWED: Option<FollowedPlan>[] = [
  { value: 'yes', label: 'kept the plan' },
  { value: 'partly', label: 'partly' },
  { value: 'no', label: 'did not' },
];
const REPEAT: Option<WouldRepeat>[] = [
  { value: 'yes', label: 'would decide the same' },
  { value: 'no', label: 'would not' },
  { value: 'unsure', label: 'unsure' },
];

const EMPTY = {
  what: '', stake: null as Stake | null, reversible: null as Reversible | null, confidence: '',
  lastDays: null as LastDays | null, pressures: [] as Pressure[], sleepHours: '',
  energy: null as number | null, feeling: null as Feeling | null, plan: '',
};


function toNumber(text: string): number | undefined {
  return text.trim() === '' ? undefined : Number(text);
}

function labelOf<T>(options: Option<T>[], value: T | null): string | null {
  return value === null ? null : options.find(o => o.value === value)?.label ?? null;
}

function Row({ prompt, children }: { prompt: string; children: React.ReactNode }) {
  return (
    <div className={styles.question}>
      <p className={styles.prompt}>{prompt}</p>
      <div className={styles.answers}>{children}</div>
    </div>
  );
}

function Choice({ pressed, onClick, label }: { pressed: boolean; onClick: () => void; label: string }) {
  return (
    <button type="button" aria-pressed={pressed} onClick={onClick} className={styles.choice}>
      {label}
    </button>
  );
}

/** One of several, or none: pressing the chosen one again clears it. */
function OneOf<T>({ options, value, onChange }: { options: Option<T>[]; value: T | null; onChange: (v: T | null) => void }) {
  return <>{options.map(o => (
    <Choice key={String(o.value)} label={o.label} pressed={value === o.value}
            onClick={() => onChange(value === o.value ? null : o.value)} />
  ))}</>;
}

export function DecisionsScreen() {
  const { data, isPending, isError, refetch } = useDecisions();
  const create = useCreateDecision();
  const [draft, setDraft] = React.useState(EMPTY);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const set = <K extends keyof typeof EMPTY>(key: K, value: (typeof EMPTY)[K]) =>
    setDraft(d => ({ ...d, [key]: value }));

  if (isPending) return <LoadingState label="Iris is opening your decisions…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  const canSave = draft.what.trim() !== '' && !create.isPending;
  const togglePressure = (p: Pressure) =>
    set('pressures', draft.pressures.includes(p) ? draft.pressures.filter(x => x !== p) : [...draft.pressures, p]);

  const save = async () => {
    setSaveError(null);
    const input: DecisionCreate = {
      what: draft.what.trim(),
      stake: draft.stake ?? undefined,
      reversible: draft.reversible ?? undefined,
      confidence: toNumber(draft.confidence),
      lastDays: draft.lastDays ?? undefined,
      pressures: draft.pressures,
      sleepHours: toNumber(draft.sleepHours),
      energy: draft.energy ?? undefined,
      feeling: draft.feeling ?? undefined,
      plan: draft.plan.trim() || undefined,
    };
    try {
      await create.mutateAsync(input);
      setDraft(EMPTY);
    } catch (err) {
      // The draft stays and the owner is told, as on the journal.
      setSaveError(err instanceof Error ? err.message : String(err));
    }
  };

  const open = data.decisions.filter(d => d.closedAt === null);
  const closed = data.decisions.filter(d => d.closedAt !== null);

  return (
    <Page title="Decisions" width="wide"
      description="Record a decision while the facts are fresh: a job, a move, a purchase, a conversation, a plan. The small ones too, so the big ones have something to compare against. Only the first line is needed.">
    <div className={styles.split}>
      <section aria-label="Record a decision" className={styles.form}>
        <div className={styles.questions}>
          <Row prompt="What are you deciding?">
            <input aria-label="What" value={draft.what} onChange={e => set('what', e.target.value)} className={styles.wide} />
          </Row>
          <Row prompt="What's at stake if it goes wrong?">
            <OneOf options={STAKES} value={draft.stake} onChange={v => set('stake', v)} />
            <span className={styles.subPrompt}>Can you undo it?</span>
            <OneOf options={REVERSIBLE} value={draft.reversible} onChange={v => set('reversible', v)} />
          </Row>
          <Row prompt="How sure are you it works out?">
            <input aria-label="How sure (%)" type="number" min={0} max={100} step={5} value={draft.confidence}
                   onChange={e => set('confidence', e.target.value)} className={styles.number} />
            <span className={styles.unit}>%</span>
          </Row>
          <Row prompt="What did the last few days hold?">
            <OneOf options={LAST_DAYS} value={draft.lastDays} onChange={v => set('lastDays', v)} />
          </Row>
          <Row prompt="Is anything pushing you to decide now?">
            {PRESSURES.map(o => (
              <Choice key={o.value} label={o.label} pressed={draft.pressures.includes(o.value)}
                      onClick={() => togglePressure(o.value)} />
            ))}
            <span className={styles.unit}>Any, or none</span>
          </Row>
          <Row prompt="How are you?">
            <input aria-label="Hours slept" type="number" min={0} max={24} step="0.5" value={draft.sleepHours}
                   onChange={e => set('sleepHours', e.target.value)} className={styles.number} />
            <span className={styles.unit}>hours slept</span>
            <div className={styles.scale} role="group" aria-label="Energy">
              {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(n => (
                <button key={n} aria-label={`energy ${n}`} aria-pressed={n === draft.energy}
                        type="button" className={styles.chip}
                        onClick={() => set('energy', n === draft.energy ? null : n)}>{n}</button>
              ))}
            </div>
            <span className={styles.subPrompt}>Feeling</span>
            <OneOf options={FEELINGS} value={draft.feeling} onChange={v => set('feeling', v)} />
          </Row>
          <Row prompt="What would make you stop or change course?">
            <input aria-label="Plan" value={draft.plan} onChange={e => set('plan', e.target.value)} className={styles.wide} />
          </Row>
        </div>

        <div className={styles.submit}>
          <Button variant="primary" onClick={save} disabled={!canSave}>{create.isPending ? 'Saving…' : 'Record decision'}</Button>
        </div>
        {saveError && <p role="alert" className={styles.error}>Not saved: {saveError}</p>}
      </section>

      <aside aria-label="Your decisions" className={styles.aside}>
        <h2 className={styles.asideTitle}>Waiting to hear how it went ({open.length})</h2>
        {open.length === 0 && <p className={styles.muted}>Nothing open.</p>}
        <div className={styles.list}>{open.map(d => <OpenDecision key={d.id} decision={d} />)}</div>
        {closed.length > 0 && (
          <>
            <h2 className={styles.asideTitle}>Closed ({closed.length})</h2>
            <div className={styles.list}>{closed.map(d => <ClosedDecision key={d.id} decision={d} />)}</div>
          </>
        )}
      </aside>
    </div>
    </Page>
  );
}

function Facts({ d }: { d: Decision }) {
  const stake = labelOf(STAKES, d.stake);
  const undo = labelOf(REVERSIBLE, d.reversible);
  const facts = [
    stake ? `at stake: ${stake}` : null,
    undo ? `undo: ${undo}` : null,
    d.confidence !== null ? `${d.confidence}% sure` : null,
    labelOf(LAST_DAYS, d.lastDays) ? `after ${labelOf(LAST_DAYS, d.lastDays)}` : null,
    d.pressures.length ? `pushed by ${d.pressures.map(p => labelOf(PRESSURES, p)).join(', ')}` : null,
    d.sleepHours !== null ? `${d.sleepHours}h sleep` : null,
    d.energy !== null ? `energy ${d.energy}` : null,
    labelOf(FEELINGS, d.feeling),
  ].filter(Boolean);
  return facts.length ? <p className={styles.facts}>{facts.join('; ')}</p> : null;
}

function OpenDecision({ decision: d }: { decision: Decision }) {
  const record = useRecordOutcome();
  const [outcome, setOutcome] = React.useState('');
  const [followed, setFollowed] = React.useState<FollowedPlan | null>(null);
  const [repeat, setRepeat] = React.useState<WouldRepeat | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const save = async () => {
    setError(null);
    try {
      await record.mutateAsync({ id: d.id, outcome: outcome.trim(), followedPlan: followed, wouldRepeat: repeat });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <article className={styles.decision} aria-label={`open decision: ${d.what}`}>
      <span className={styles.when}>{formatEventDate(d.decidedOn)}</span>
      <p className={styles.what}>{d.what}</p>
      <Facts d={d} />
      {d.plan && <p className={styles.muted}>Would stop if: {d.plan}</p>}
      <textarea aria-label={`How did it go: ${d.what}`} placeholder="How did it go?" rows={2} value={outcome}
                onChange={e => setOutcome(e.target.value)} className={styles.outcome} />
      {d.plan && (
        <div className={styles.answers}>
          <OneOf options={FOLLOWED} value={followed} onChange={setFollowed} />
        </div>
      )}
      <div className={styles.answers}>
        <OneOf options={REPEAT} value={repeat} onChange={setRepeat} />
        <Button size="sm" onClick={save} disabled={outcome.trim() === '' || record.isPending} className={styles.close}>
          {record.isPending ? 'Saving…' : 'Close'}</Button>
      </div>
      {error && <p role="alert" className={styles.error}>Not saved: {error}</p>}
    </article>
  );
}

function ClosedDecision({ decision: d }: { decision: Decision }) {
  const verdicts = [labelOf(FOLLOWED, d.followedPlan), labelOf(REPEAT, d.wouldRepeat)].filter(Boolean);
  return (
    <article className={styles.decision} aria-label={`closed decision: ${d.what}`}>
      <span className={styles.when}>{formatEventDate(d.decidedOn)}{verdicts.length ? `, ${verdicts.join(', ')}` : ''}</span>
      <p className={styles.what}>{d.what}</p>
      <Facts d={d} />
      <p className={styles.muted}>{d.outcome}</p>
    </article>
  );
}

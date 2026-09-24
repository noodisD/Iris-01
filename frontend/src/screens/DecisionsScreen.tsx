import React from 'react';
import { useCreateDecision, useDecisions, useRecordOutcome } from '@/hooks/useDecisions';
import { LoadingState, ErrorState } from '@/components/states';
import { formatEventDate } from '@/lib/dates';
import type {
  Decision, DecisionCreate, Feeling, FollowedPlan, LastDays, Pressure, Reversible, Stake, WouldRepeat,
} from '@/types/api';

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

const mono: React.CSSProperties = {
  fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.1em', textTransform: 'uppercase',
};
const field: React.CSSProperties = {
  background: 'transparent', border: 'none', borderBottom: '1px solid var(--line)', outline: 'none',
  color: 'var(--ink)', fontFamily: 'var(--serif)', fontSize: 18, padding: '4px 0',
};

function toNumber(text: string): number | undefined {
  return text.trim() === '' ? undefined : Number(text);
}

function labelOf<T>(options: Option<T>[], value: T | null): string | null {
  return value === null ? null : options.find(o => o.value === value)?.label ?? null;
}

function Row({ n, prompt, children }: { n: number; prompt: string; children: React.ReactNode }) {
  return (
    <div className="col" style={{ gap: 8, padding: '14px 0', borderBottom: '1px solid var(--line)' }}>
      <div className="row" style={{ alignItems: 'baseline', gap: 12 }}>
        <span style={{ ...mono, minWidth: 16 }}>0{n}</span>
        <span className="serif ital" style={{ fontSize: 18, color: 'var(--ink-3)' }}>{prompt}</span>
      </div>
      <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap', paddingLeft: 28 }}>{children}</div>
    </div>
  );
}

function Choice({ pressed, onClick, label }: { pressed: boolean; onClick: () => void; label: string }) {
  return (
    <button aria-pressed={pressed} onClick={onClick}
      style={{ fontFamily: 'var(--mono)', fontSize: 11, padding: '4px 10px', borderRadius: 999, cursor: 'pointer',
               border: `1px solid ${pressed ? 'var(--sage)' : 'var(--line)'}`,
               background: pressed ? 'var(--sage)' : 'transparent', color: pressed ? '#14140f' : 'var(--ink-3)' }}>
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
    <div className="row" style={{ height: '100%' }}>
      <div className="col" style={{ flex: 1, padding: '32px 56px 40px', minWidth: 0, overflow: 'auto' }}>
        <div className="col" style={{ gap: 6, marginBottom: 28 }}>
          <div className="kicker">decisions · before you decide</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
            A few facts,<br /><span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>while they're true.</span>
          </h1>
          <p style={{ margin: '8px 0 0', maxWidth: 560, fontSize: 13, color: 'var(--ink-3)', lineHeight: 1.55 }}>
            Any decision: a job, a move, a purchase, a conversation, a plan. The small ones too — without them there is
            nothing to compare the big ones against. Only the first line is needed.
          </p>
        </div>

        <div className="col" style={{ maxWidth: 720 }}>
          <Row n={1} prompt="What are you deciding?">
            <input aria-label="What" value={draft.what} onChange={e => set('what', e.target.value)}
                   style={{ ...field, flex: 1, minWidth: 280 }} />
          </Row>
          <Row n={2} prompt="What's at stake if it goes wrong?">
            <OneOf options={STAKES} value={draft.stake} onChange={v => set('stake', v)} />
            <span style={{ ...mono, width: '100%', marginTop: 6 }}>can you undo it?</span>
            <OneOf options={REVERSIBLE} value={draft.reversible} onChange={v => set('reversible', v)} />
          </Row>
          <Row n={3} prompt="How sure are you it works out?">
            <input aria-label="How sure (%)" type="number" min={0} max={100} step={5} value={draft.confidence}
                   onChange={e => set('confidence', e.target.value)} style={{ ...field, width: 70 }} />
            <span style={mono}>%</span>
          </Row>
          <Row n={4} prompt="What did the last few days hold?">
            <OneOf options={LAST_DAYS} value={draft.lastDays} onChange={v => set('lastDays', v)} />
          </Row>
          <Row n={5} prompt="Is anything pushing you to decide now?">
            {PRESSURES.map(o => (
              <Choice key={o.value} label={o.label} pressed={draft.pressures.includes(o.value)}
                      onClick={() => togglePressure(o.value)} />
            ))}
            <span style={{ fontSize: 12, color: 'var(--ink-4)' }}>any, or none</span>
          </Row>
          <Row n={6} prompt="How are you?">
            <input aria-label="Hours slept" type="number" min={0} max={24} step="0.5" value={draft.sleepHours}
                   onChange={e => set('sleepHours', e.target.value)} style={{ ...field, width: 60 }} />
            <span style={{ ...mono, marginRight: 8 }}>hours slept</span>
            <div className="row" style={{ gap: 4, alignItems: 'center' }}>
              {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(n => (
                <button key={n} aria-label={`energy ${n}`} aria-pressed={n === draft.energy}
                        onClick={() => set('energy', n === draft.energy ? null : n)}
                        style={{ width: 22, height: 22, borderRadius: '50%', padding: 0, cursor: 'pointer', fontFamily: 'var(--mono)', fontSize: 10,
                                 border: `1px solid ${n === draft.energy ? 'var(--sage)' : 'var(--line)'}`,
                                 background: n === draft.energy ? 'var(--sage)' : 'transparent',
                                 color: n === draft.energy ? '#14140f' : 'var(--ink-3)' }}>{n}</button>
              ))}
            </div>
            <span style={{ ...mono, width: '100%', marginTop: 6 }}>feeling</span>
            <OneOf options={FEELINGS} value={draft.feeling} onChange={v => set('feeling', v)} />
          </Row>
          <Row n={7} prompt="What would make you stop or change course?">
            <input aria-label="Plan" value={draft.plan} onChange={e => set('plan', e.target.value)}
                   style={{ ...field, flex: 1, minWidth: 280 }} />
          </Row>
        </div>

        <div className="row" style={{ gap: 12, marginTop: 18, maxWidth: 720, justifyContent: 'flex-end' }}>
          <button className="btn primary" onClick={save} disabled={!canSave}>
            {create.isPending ? 'Saving…' : 'Record decision'}
          </button>
        </div>
        {saveError && <div role="alert" style={{ marginTop: 8, fontSize: 12, color: 'var(--rose)', fontFamily: 'var(--mono)' }}>Not saved: {saveError}</div>}
      </div>

      <aside style={{ width: 380, flexShrink: 0, borderLeft: '1px dashed var(--line)', padding: '32px 28px', overflow: 'auto' }}>
        <div className="kicker" style={{ marginBottom: 14 }}>waiting to hear how it went · {open.length}</div>
        {open.length === 0 && <div style={{ fontSize: 12, color: 'var(--ink-4)' }}>Nothing open.</div>}
        <div className="col" style={{ gap: 18 }}>
          {open.map(d => <OpenDecision key={d.id} decision={d} />)}
        </div>
        {closed.length > 0 && (
          <>
            <div className="kicker" style={{ margin: '28px 0 14px' }}>closed · {closed.length}</div>
            <div className="col" style={{ gap: 14 }}>
              {closed.map(d => <ClosedDecision key={d.id} decision={d} />)}
            </div>
          </>
        )}
      </aside>
    </div>
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
  return facts.length ? <div style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--mono)', lineHeight: 1.5 }}>{facts.join(' · ')}</div> : null;
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
    <article className="col" style={{ gap: 6 }} aria-label={`open decision: ${d.what}`}>
      <span style={{ ...mono, color: 'var(--ink-3)' }}>{formatEventDate(d.decidedOn)}</span>
      <div style={{ fontSize: 13, color: 'var(--ink)' }}>{d.what}</div>
      <Facts d={d} />
      {d.plan && <div style={{ fontSize: 12, color: 'var(--ink-3)', fontStyle: 'italic' }}>would stop if: {d.plan}</div>}
      <textarea aria-label={`How did it go: ${d.what}`} placeholder="how did it go?" rows={2} value={outcome}
                onChange={e => setOutcome(e.target.value)} style={{ ...field, fontSize: 14, resize: 'none' }} />
      {d.plan && (
        <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
          <OneOf options={FOLLOWED} value={followed} onChange={setFollowed} />
        </div>
      )}
      <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <OneOf options={REPEAT} value={repeat} onChange={setRepeat} />
        <button className="btn" onClick={save} disabled={outcome.trim() === '' || record.isPending}
                style={{ marginLeft: 'auto' }}>{record.isPending ? 'Saving…' : 'Close'}</button>
      </div>
      {error && <div role="alert" style={{ fontSize: 11, color: 'var(--rose)', fontFamily: 'var(--mono)' }}>Not saved: {error}</div>}
    </article>
  );
}

function ClosedDecision({ decision: d }: { decision: Decision }) {
  const verdicts = [labelOf(FOLLOWED, d.followedPlan), labelOf(REPEAT, d.wouldRepeat)].filter(Boolean);
  return (
    <article className="col" style={{ gap: 4 }}>
      <span style={{ ...mono, color: 'var(--ink-3)' }}>{formatEventDate(d.decidedOn)}{verdicts.length ? ` · ${verdicts.join(' · ')}` : ''}</span>
      <div style={{ fontSize: 12, color: 'var(--ink-2)' }}>{d.what}</div>
      <Facts d={d} />
      <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>{d.outcome}</div>
    </article>
  );
}

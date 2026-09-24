import React from 'react';
import { useCreateDecision, useDecisions, useRecordOutcome } from '@/hooks/useDecisions';
import { LoadingState, ErrorState } from '@/components/states';
import { formatEventDate } from '@/lib/dates';
import type { Decision, DecisionCreate, FollowedPlan, LastDays } from '@/types/api';

/**
 * A log of risky commitments, filled in at the moment one is made.
 *
 * Looking back through the writing could not say when a commitment grew too
 * large, because the facts that would say so were almost never written down:
 * how much of what you had was at stake, whether any was borrowed, what the
 * days before held, money needed soon, sleep. These are those facts, asked at
 * the time. Only the first is required: a form that demands everything in the
 * moment gets skipped, and a skipped entry helps less than a partial one.
 */

const LAST_DAYS: { value: LastDays; label: string }[] = [
  { value: 'big_loss', label: 'a big loss' },
  { value: 'big_win', label: 'a big win' },
  { value: 'neither', label: 'neither' },
];

const FOLLOWED: { value: FollowedPlan; label: string }[] = [
  { value: 'yes', label: 'kept the plan' },
  { value: 'partly', label: 'partly' },
  { value: 'no', label: 'did not' },
];

const EMPTY = {
  what: '', sharePct: '', borrowed: false, lastDays: null as LastDays | null,
  moneyNeededFor: '', moneyNeededBy: '', sleepHours: '', energy: null as number | null, plan: '',
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

function Row({ n, prompt, children }: { n: number; prompt: string; children: React.ReactNode }) {
  return (
    <div className="col" style={{ gap: 8, padding: '14px 0', borderBottom: '1px solid var(--line)' }}>
      <div className="row" style={{ alignItems: 'baseline', gap: 12 }}>
        <span style={{ ...mono, minWidth: 16 }}>0{n}</span>
        <span className="serif ital" style={{ fontSize: 18, color: 'var(--ink-3)' }}>{prompt}</span>
      </div>
      <div className="row" style={{ gap: 12, alignItems: 'center', flexWrap: 'wrap', paddingLeft: 28 }}>{children}</div>
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

export function DecisionsScreen() {
  const { data, isPending, isError, refetch } = useDecisions();
  const create = useCreateDecision();
  const [draft, setDraft] = React.useState(EMPTY);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const set = <K extends keyof typeof EMPTY>(key: K, value: (typeof EMPTY)[K]) =>
    setDraft(d => ({ ...d, [key]: value }));

  if (isPending) return <LoadingState label="Iris is opening your decisions…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  // A date for money needed means nothing without what it is needed for.
  const moneyIncomplete = draft.moneyNeededBy !== '' && draft.moneyNeededFor.trim() === '';
  const canSave = draft.what.trim() !== '' && !moneyIncomplete && !create.isPending;

  const save = async () => {
    setSaveError(null);
    const input: DecisionCreate = {
      what: draft.what.trim(),
      borrowed: draft.borrowed,
      sharePct: toNumber(draft.sharePct),
      lastDays: draft.lastDays ?? undefined,
      moneyNeededFor: draft.moneyNeededFor.trim() || undefined,
      moneyNeededBy: draft.moneyNeededBy || undefined,
      sleepHours: toNumber(draft.sleepHours),
      energy: draft.energy ?? undefined,
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
          <div className="kicker">decisions · before you commit</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
            A few facts,<br /><span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>while they're true.</span>
          </h1>
          <p style={{ margin: '8px 0 0', maxWidth: 560, fontSize: 13, color: 'var(--ink-3)', lineHeight: 1.55 }}>
            Every commitment, not only the big ones. Without the ordinary ones there is nothing to compare the big ones against.
            Only the first line is needed.
          </p>
        </div>

        <div className="col" style={{ maxWidth: 720 }}>
          <Row n={1} prompt="What are you committing to?">
            <input aria-label="What" value={draft.what} onChange={e => set('what', e.target.value)}
                   style={{ ...field, flex: 1, minWidth: 280 }} />
          </Row>
          <Row n={2} prompt="How much of what you have?">
            <input aria-label="Share of what you have (%)" type="number" min={0} step="any" value={draft.sharePct}
                   onChange={e => set('sharePct', e.target.value)} style={{ ...field, width: 90 }} />
            <span style={mono}>%</span>
            <label className="row" style={{ gap: 6, alignItems: 'center', fontSize: 13, color: 'var(--ink-3)' }}>
              <input type="checkbox" checked={draft.borrowed} onChange={e => set('borrowed', e.target.checked)} />
              some of it is borrowed
            </label>
          </Row>
          <Row n={3} prompt="What did the last few days hold?">
            {LAST_DAYS.map(o => (
              <Choice key={o.value} label={o.label} pressed={draft.lastDays === o.value}
                      onClick={() => set('lastDays', draft.lastDays === o.value ? null : o.value)} />
            ))}
          </Row>
          <Row n={4} prompt="Is money needed soon for something?">
            <input aria-label="Money needed for" placeholder="for what" value={draft.moneyNeededFor}
                   onChange={e => set('moneyNeededFor', e.target.value)} style={{ ...field, flex: 1, minWidth: 200 }} />
            <input aria-label="Money needed by" type="date" value={draft.moneyNeededBy}
                   onChange={e => set('moneyNeededBy', e.target.value)} style={{ ...field, fontSize: 14 }} />
          </Row>
          <Row n={5} prompt="How did you sleep, and how is your energy?">
            <input aria-label="Hours slept" type="number" min={0} max={24} step="0.5" value={draft.sleepHours}
                   onChange={e => set('sleepHours', e.target.value)} style={{ ...field, width: 70 }} />
            <span style={mono}>hours</span>
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
          </Row>
          <Row n={6} prompt="Your plan: the way out, and when you'd stop.">
            <input aria-label="Plan" value={draft.plan} onChange={e => set('plan', e.target.value)}
                   style={{ ...field, flex: 1, minWidth: 280 }} />
          </Row>
        </div>

        <div className="row" style={{ gap: 12, marginTop: 18, maxWidth: 720, justifyContent: 'flex-end', alignItems: 'center' }}>
          {moneyIncomplete && <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Say what the money is needed for.</span>}
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
  const facts = [
    d.sharePct !== null ? `${d.sharePct}%${d.borrowed ? ' · borrowed' : ''}` : d.borrowed ? 'borrowed' : null,
    d.lastDays ? LAST_DAYS.find(o => o.value === d.lastDays)?.label : null,
    d.moneyNeededFor ? `needed: ${d.moneyNeededFor}${d.moneyNeededBy ? ` by ${formatEventDate(d.moneyNeededBy)}` : ''}` : null,
    d.sleepHours !== null ? `${d.sleepHours}h sleep` : null,
    d.energy !== null ? `energy ${d.energy}` : null,
  ].filter(Boolean);
  return facts.length ? <div style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--mono)' }}>{facts.join(' · ')}</div> : null;
}

function OpenDecision({ decision: d }: { decision: Decision }) {
  const record = useRecordOutcome();
  const [outcome, setOutcome] = React.useState('');
  const [followed, setFollowed] = React.useState<FollowedPlan | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const save = async () => {
    setError(null);
    try {
      await record.mutateAsync({ id: d.id, outcome: outcome.trim(), followedPlan: followed });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <article className="col" style={{ gap: 6 }} aria-label={`open decision: ${d.what}`}>
      <span style={{ ...mono, color: 'var(--ink-3)' }}>{formatEventDate(d.decidedOn)}</span>
      <div style={{ fontSize: 13, color: 'var(--ink)' }}>{d.what}</div>
      <Facts d={d} />
      {d.plan && <div style={{ fontSize: 12, color: 'var(--ink-3)', fontStyle: 'italic' }}>plan: {d.plan}</div>}
      <textarea aria-label={`How did it go: ${d.what}`} placeholder="how did it go?" rows={2} value={outcome}
                onChange={e => setOutcome(e.target.value)}
                style={{ ...field, fontSize: 14, resize: 'none', borderBottom: '1px solid var(--line)' }} />
      <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        {d.plan && FOLLOWED.map(o => (
          <Choice key={o.value} label={o.label} pressed={followed === o.value}
                  onClick={() => setFollowed(followed === o.value ? null : o.value)} />
        ))}
        <button className="btn" onClick={save} disabled={outcome.trim() === '' || record.isPending}
                style={{ marginLeft: 'auto' }}>{record.isPending ? 'Saving…' : 'Close'}</button>
      </div>
      {error && <div role="alert" style={{ fontSize: 11, color: 'var(--rose)', fontFamily: 'var(--mono)' }}>Not saved: {error}</div>}
    </article>
  );
}

function ClosedDecision({ decision: d }: { decision: Decision }) {
  const kept = d.followedPlan ? FOLLOWED.find(o => o.value === d.followedPlan)?.label : null;
  return (
    <article className="col" style={{ gap: 4 }}>
      <span style={{ ...mono, color: 'var(--ink-3)' }}>{formatEventDate(d.decidedOn)}{kept ? ` · ${kept}` : ''}</span>
      <div style={{ fontSize: 12, color: 'var(--ink-2)' }}>{d.what}</div>
      <Facts d={d} />
      <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>{d.outcome}</div>
    </article>
  );
}

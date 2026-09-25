import React from 'react';
import { Link, NavLink, useParams } from 'react-router-dom';
import { useOccasionVerdict, usePattern, usePatterns, usePatternVerdict } from '@/hooks/usePatterns';
import { LoadingState, ErrorState } from '@/components/states';
import { formatEventDate } from '@/lib/dates';
import type { Occasion, OccasionVerdictValue, PatternDetail, PatternSummary, PatternVerdictValue } from '@/types/api';

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

const mono: React.CSSProperties = {
  fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.1em', textTransform: 'uppercase',
};

const PATTERN_VERDICTS: { value: PatternVerdictValue; label: string }[] = [
  { value: 'rings_true', label: 'rings true' },
  { value: 'does_not', label: "doesn't ring true" },
  { value: 'unsure', label: 'unsure' },
];
const OCCASION_VERDICTS: { value: OccasionVerdictValue; label: string }[] = [
  { value: 'yes', label: 'this one' },
  { value: 'no', label: 'not this' },
  { value: 'unsure', label: 'unsure' },
];

function Choice({ pressed, onClick, label, disabled }: { pressed: boolean; onClick: () => void; label: string; disabled?: boolean }) {
  return (
    <button aria-pressed={pressed} onClick={onClick} disabled={disabled}
      style={{ fontFamily: 'var(--mono)', fontSize: 11, padding: '3px 9px', borderRadius: 999, cursor: 'pointer',
               border: `1px solid ${pressed ? 'var(--sage)' : 'var(--line)'}`,
               background: pressed ? 'var(--sage)' : 'transparent', color: pressed ? '#14140f' : 'var(--ink-3)' }}>
      {label}
    </button>
  );
}

function counts(p: PatternSummary): string {
  if (p.occasions === 0) return 'none found';
  const parts = [`${p.tones.worse} worse`, `${p.tones.better} better`];
  if (p.tones.mixed) parts.push(`${p.tones.mixed} mixed`);
  return parts.join(' · ');
}

export function PatternsScreen() {
  const { id } = useParams<{ id: string }>();
  const { data, isPending, isError, refetch } = usePatterns();
  if (isPending) return <LoadingState label="Iris is opening the library…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  const sorted = [...data.patterns].sort((a, b) => b.occasions - a.occasions || a.name.localeCompare(b.name));

  return (
    <div className="row" style={{ height: '100%' }}>
      <nav aria-label="Patterns" style={{ width: 320, flexShrink: 0, borderRight: '1px dashed var(--line)', padding: '32px 20px', overflow: 'auto' }}>
        <div className="kicker" style={{ marginBottom: 6 }}>patterns · a general library</div>
        <p style={{ margin: '0 0 18px', fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.5 }}>
          Patterns known in general, and how many times each turns up in your own writing.
        </p>
        <div className="col" style={{ gap: 2 }}>
          {sorted.map(p => (
            <NavLink key={p.id} to={`/patterns/${p.id}`}
              style={({ isActive }) => ({
                display: 'block', padding: '8px 10px', borderRadius: 6, textDecoration: 'none',
                background: isActive ? 'rgba(169,200,163,0.08)' : 'transparent',
                opacity: p.verdict?.verdict === 'does_not' ? 0.55 : 1,
              })}>
              <div style={{ fontSize: 13, color: 'var(--ink)' }}>{p.name}</div>
              <div style={{ fontSize: 11, color: p.occasions ? 'var(--ink-3)' : 'var(--ink-4)', fontFamily: 'var(--mono)' }}>
                {counts(p)}{p.verdict ? ` · ${PATTERN_VERDICTS.find(v => v.value === p.verdict!.verdict)?.label}` : ''}
              </div>
            </NavLink>
          ))}
        </div>
      </nav>
      <main style={{ flex: 1, minWidth: 0, overflow: 'auto', padding: '32px 48px 40px' }}>
        {id ? <PatternView id={id} /> : (
          <div className="col" style={{ gap: 10, maxWidth: 560 }}>
            <div className="kicker">discovery</div>
            <h1 className="serif" style={{ margin: 0, fontSize: 48, lineHeight: 1 }}>Pick a pattern.</h1>
            <p style={{ fontSize: 14, color: 'var(--ink-3)', lineHeight: 1.6 }}>
              Each one shows the occasions in your writing that fit it, split by how they went, and what else was true on each
              side. You decide whether an occasion really belongs, and whether the pattern rings true at all.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}

function PatternView({ id }: { id: string }) {
  const { data, isPending, isError, refetch } = usePattern(id);
  const verdict = usePatternVerdict(id);
  if (isPending) return <LoadingState label="Iris is gathering the occasions…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;
  const { pattern: p } = data;
  const current = data.verdict?.verdict ?? null;

  const counted = data.occasions.filter(o => o.ownerVerdict !== 'no');
  const side = (tone: Occasion['tone']) => counted.filter(o => o.tone === tone);
  const rejected = data.occasions.filter(o => o.ownerVerdict === 'no');
  const labelledBy = [...new Set(data.occasions.map(o => o.labelledBy).filter(Boolean))];

  return (
    <div className="col" style={{ gap: 18, maxWidth: 980 }}>
      <div className="col" style={{ gap: 6 }}>
        <div className="kicker">
          {p.evidence ? `the idea: ${p.evidence}` : 'a pattern from the library'}
          {p.source && <> · <a href={p.source} target="_blank" rel="noreferrer" style={{ color: 'inherit' }}>where it comes from</a></>}
        </div>
        <h1 className="serif" style={{ margin: 0, fontSize: 44, lineHeight: 1, letterSpacing: '-0.02em' }}>{p.name}</h1>
        <p style={{ margin: 0, fontSize: 15, color: 'var(--ink-2)', maxWidth: 720, lineHeight: 1.55 }}>{p.statement}</p>
        {p.basis && <p style={{ margin: 0, fontSize: 12, color: 'var(--ink-3)', maxWidth: 720 }}>{p.basis}</p>}
      </div>

      <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={mono}>does it ring true?</span>
        {PATTERN_VERDICTS.map(v => (
          <Choice key={v.value} label={v.label} pressed={current === v.value} disabled={verdict.isPending}
                  onClick={() => verdict.mutate(v.value)} />
        ))}
      </div>

      {data.occasions.length === 0 ? (
        <p style={{ fontSize: 13, color: 'var(--ink-3)' }}>
          None found in the current reading of your archive. That can mean it is rare for you, or that the labelling
          missed it: labelling misses some occasions and includes some that do not belong.
        </p>
      ) : (
        <>
          <div className="row" style={{ gap: 28, alignItems: 'flex-start' }}>
            <Side title="went worse" occasions={side('worse')} patternId={p.id} />
            <Side title="went better" occasions={side('better')} patternId={p.id} />
          </div>
          {side('mixed').length > 0 && <Side title="mixed" occasions={side('mixed')} patternId={p.id} />}
          <Distinctive data={data} />
          {rejected.length > 0 && (
            <div style={{ opacity: 0.6 }}><Side title="you said: not this pattern" occasions={rejected} patternId={p.id} /></div>
          )}
          {labelledBy.length > 0 && <div style={mono}>labelled by: {labelledBy.join(', ')}</div>}
        </>
      )}
    </div>
  );
}

function Side({ title, occasions, patternId }: { title: string; occasions: Occasion[]; patternId: string }) {
  return (
    <section aria-label={title} className="col" style={{ flex: 1, minWidth: 0, gap: 12 }}>
      <div className="kicker">{title} · {occasions.length}</div>
      {occasions.map(o => <OccasionCard key={o.id} occasion={o} patternId={patternId} />)}
    </section>
  );
}

function OccasionCard({ occasion: o, patternId }: { occasion: Occasion; patternId: string }) {
  const verdict = useOccasionVerdict(patternId);
  return (
    <article aria-label={`occasion: ${o.situation}`} className="col"
             style={{ gap: 6, padding: '12px 14px', border: '1px solid var(--line)', borderRadius: 8 }}>
      <span style={{ ...mono, color: 'var(--ink-3)' }}>{o.occurredOn ? formatEventDate(o.occurredOn) : 'undated'}</span>
      <div style={{ fontSize: 13, color: 'var(--ink)' }}>{o.situation}</div>
      <div style={{ fontSize: 12, color: 'var(--ink-2)' }}>{o.response}</div>
      {o.outcome && <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>→ {o.outcome}</div>}
      {o.citations.slice(0, 2).map((c, i) => (
        <blockquote key={i} style={{ margin: 0, paddingLeft: 10, borderLeft: '2px solid var(--line)', fontSize: 12, color: 'var(--ink-3)', fontStyle: 'italic' }}>
          {c.text}{' '}
          {c.sourceType === 'reflection' && (
            <Link to={`/journal?entry=${c.entryId}`} style={{ fontStyle: 'normal', fontSize: 11, color: 'var(--sage)' }}>open entry</Link>
          )}
        </blockquote>
      ))}
      <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        {OCCASION_VERDICTS.map(v => (
          <Choice key={v.value} label={v.label} pressed={o.ownerVerdict === v.value} disabled={verdict.isPending}
                  onClick={() => verdict.mutate({ occasionId: o.id, verdict: o.ownerVerdict === v.value ? null : v.value })} />
        ))}
      </div>
      {o.verdictNote && <div style={{ fontSize: 11, color: 'var(--ink-4)' }}>{o.verdictNote}</div>}
    </article>
  );
}

function Distinctive({ data }: { data: PatternDetail }) {
  if (data.distinctive.length === 0) return null;
  return (
    <section aria-label="what else differed" className="col" style={{ gap: 8 }}>
      <div className="kicker">what else differed between the sides</div>
      {data.distinctive.map(d => (
        <div key={d.patternId} className="row" style={{ gap: 12, alignItems: 'baseline', fontSize: 13 }}>
          <Link to={`/patterns/${d.patternId}`} style={{ color: 'var(--ink)', minWidth: 280 }}>{d.name}</Link>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-3)' }}>{d.worse} worse · {d.better} better</span>
        </div>
      ))}
      <div style={{ fontSize: 11, color: 'var(--ink-4)' }}>
        Differences of two or more occasions. A difference between two sets of occasions, not a cause and not advice.
      </div>
    </section>
  );
}

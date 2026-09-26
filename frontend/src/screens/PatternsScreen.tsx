import { Link, NavLink, useParams } from 'react-router-dom';
import { useOccasionVerdict, usePattern, usePatterns, usePatternVerdict } from '@/hooks/usePatterns';
import { LoadingState, ErrorState } from '@/components/states';
import { formatEventDate } from '@/lib/dates';
import type { Occasion, OccasionVerdictValue, PatternDetail, PatternSummary, PatternVerdictValue } from '@/types/api';
import { Badge, ChoiceGroup, Panel } from '@/ui';
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

function counts(p: PatternSummary): string {
  if (p.occasions === 0) return 'none found';
  const parts = [`${p.tones.worse} worse`, `${p.tones.better} better`];
  if (p.tones.mixed) parts.push(`${p.tones.mixed} mixed`);
  return parts.join(', ');
}

export function PatternsScreen() {
  const { id } = useParams<{ id: string }>();
  const { data, isPending, isError, refetch } = usePatterns();
  if (isPending) return <LoadingState label="Iris is opening the library…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  // A library pattern is shown once it has been found in the owner's writing;
  // until then it only counts toward the line at the end of the list.
  const sorted = [...data.patterns].filter(p => p.occasions > 0)
    .sort((a, b) => b.occasions - a.occasions || a.name.localeCompare(b.name));
  const unfound = data.patterns.length - sorted.length;

  return (
    // On a phone the list and a pattern take turns; side by side from 900px.
    <div className={`${styles.split} ${id ? styles.showingDetail : ''}`}>
      <nav aria-label="Patterns" className={styles.list}>
        <h1 className={styles.listTitle}>Patterns</h1>
        <p className={styles.listNote}>Patterns known in general, and how often each turns up in your writing.</p>
        <ul className={styles.items}>
          {sorted.map(p => (
            <li key={p.id}>
              <NavLink to={`/patterns/${p.id}`}
                className={({ isActive }) => `${styles.item} ${isActive ? styles.active : ''} ${p.verdict?.verdict === 'does_not' ? styles.dimmed : ''}`}>
                <span className={styles.itemName}>{p.name}</span>
                <span className={styles.itemMeta}>
                  {counts(p)}
                  {p.verdict && <Badge tone={p.verdict.verdict === 'rings_true' ? 'confirmed' : 'neutral'}>
                    {PATTERN_VERDICTS.find(v => v.value === p.verdict!.verdict)?.label}
                  </Badge>}
                </span>
              </NavLink>
            </li>
          ))}
        </ul>
        {unfound > 0 && <p className={styles.unfound}>{unfound} more in the library, not yet found in your writing</p>}
      </nav>
      <div className={styles.detail}>
        {id ? <PatternView id={id} /> : (
          <div className={styles.pick}>
            <h2 className={styles.pickTitle}>Pick a pattern.</h2>
            <p>
              Each shows the occasions in your writing that fit it, split by how they went, and what else was true on
              each side. You decide whether an occasion really belongs, and whether the pattern rings true at all.
            </p>
          </div>
        )}
      </div>
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
    <article className={styles.pattern} aria-label={p.name}>
      <Link to="/patterns" className={styles.back}>← All patterns</Link>
      <header className={styles.patternHead}>
        <p className={styles.provenance}>
          {p.evidence ? `The idea: ${p.evidence}.` : 'A pattern from the library.'}
          {p.source && <> <a href={p.source} target="_blank" rel="noreferrer">Where it comes from</a></>}
        </p>
        <h2 className={styles.patternName}>{p.name}</h2>
        <p className={styles.statement}>{p.statement}</p>
        {p.basis && <p className={styles.basis}>{p.basis}</p>}
      </header>

      <div className={styles.verdict}>
        <span className={styles.verdictLabel}>Does it ring true?</span>
        <ChoiceGroup label="Does it ring true?" tone="confirm" options={PATTERN_VERDICTS} value={current}
          disabled={verdict.isPending} onChange={value => value && verdict.mutate(value)} />
      </div>

      {data.occasions.length === 0 ? (
        <p className={styles.none}>
          None found in the current reading of your archive. That can mean it is rare for you, or that the labelling
          missed it: labelling misses some occasions and includes some that do not belong.
        </p>
      ) : (
        <>
          <div className={styles.sides}>
            <Side title="Went worse" occasions={side('worse')} patternId={p.id} />
            <Side title="Went better" occasions={side('better')} patternId={p.id} />
          </div>
          {side('mixed').length > 0 && <Side title="Mixed" occasions={side('mixed')} patternId={p.id} />}
          <Distinctive data={data} />
          {rejected.length > 0 && (
            <div className={styles.rejected}><Side title="You said: not this pattern" occasions={rejected} patternId={p.id} /></div>
          )}
          {labelledBy.length > 0 && <p className={styles.labelled}>Labelled by {labelledBy.join(', ')}</p>}
        </>
      )}
    </article>
  );
}

function Side({ title, occasions, patternId }: { title: string; occasions: Occasion[]; patternId: string }) {
  return (
    <section aria-label={title.toLowerCase()} className={styles.side}>
      <h3 className={styles.sideTitle}>{title} ({occasions.length})</h3>
      {occasions.map(o => <OccasionCard key={o.id} occasion={o} patternId={patternId} />)}
    </section>
  );
}

function OccasionCard({ occasion: o, patternId }: { occasion: Occasion; patternId: string }) {
  const verdict = useOccasionVerdict(patternId);
  return (
    <Panel as="article" aria-label={`occasion: ${o.situation}`} tone={o.ownerVerdict === 'yes' ? 'confirmed' : undefined}>
      <span className={styles.when}>{o.occurredOn ? formatEventDate(o.occurredOn) : 'undated'}</span>
      <p className={styles.situation}>{o.situation}</p>
      <p className={styles.response}>{o.response}</p>
      {o.outcome && <p className={styles.outcome}>Then: {o.outcome}</p>}
      {o.citations.slice(0, 2).map((c, i) => (
        <blockquote key={i} className={styles.quote}>
          {c.text}{' '}
          {c.sourceType === 'reflection' && <Link to={`/journal?entry=${c.entryId}`}>open entry</Link>}
        </blockquote>
      ))}
      <ChoiceGroup label="Is this an occasion of the pattern?" options={OCCASION_VERDICTS} value={o.ownerVerdict}
        clearable disabled={verdict.isPending}
        onChange={value => verdict.mutate({ occasionId: o.id, verdict: value })} />
      {o.verdictNote && <p className={styles.noteText}>{o.verdictNote}</p>}
    </Panel>
  );
}

function Distinctive({ data }: { data: PatternDetail }) {
  if (data.distinctive.length === 0) return null;
  return (
    <section aria-label="what else differed" className={styles.differed}>
      <h3 className={styles.sideTitle}>What else differed between the sides</h3>
      <ul>
        {data.distinctive.map(d => (
          <li key={d.patternId}>
            <Link to={`/patterns/${d.patternId}`}>{d.name}</Link>
            <span className={styles.counts}>{d.worse} worse, {d.better} better</span>
          </li>
        ))}
      </ul>
      <p className={styles.noteText}>Differences of two or more occasions. A difference between two sets of occasions, not a cause and not advice.</p>
    </section>
  );
}

import { useReview } from '@/hooks/useData';
import { LoadingState, ErrorState } from '@/components/states';
import { Lens, Page, Section, Stat } from '@/ui';
import styles from './ReviewScreen.module.css';

/** Render a delta with its real sign: a hardcoded '+' turned -1.2 into '+-1.2'. */
const signed = (n: number | null) => (n === null ? 'no comparison' : n > 0 ? `+${n}` : `${n}`);

/** The week: Iris's letter, what was kept, and the energy you reported each day. */
export function ReviewScreen() {
  const { data, isLoading, isError, refetch } = useReview();
  if (isLoading) return <LoadingState label="Iris is composing your week…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  const m = data.metrics;
  const [opening, ...rest] = data.letter.split('\n\n');
  return (
    <Page title="Your week" lead={`${data.weekStart} to ${data.weekEnd}`} width="reading">
      <article className={styles.letter} aria-label="Iris's letter">
        <Lens size={32} />
        <p className={styles.opening}>{opening}</p>
        {rest.map((para, i) => <p key={i} className={styles.para}>{para}</p>)}
      </article>

      <div className={styles.stats}>
        <Stat value={m.energyAvg === null ? 'None' : m.energyAvg.toFixed(1)}
          label={m.energyAvg === null ? 'No energy reported' : `Energy you reported, ${signed(m.energyDelta)} on last week`} />
        <Stat value={`${m.habitsHit} of ${m.habitsTotal}`} label="Habits kept" />
      </div>

      <Section title="Your energy, day by day">
        <ol className={styles.days}>
          {data.days.map((d, i) => {
            const intensity = (d.energy ?? 0) / 10;
            const size = 8 + intensity * 28;
            return (
              <li key={i} className={styles.day} aria-label={`${d.shortName}: ${d.energy ?? 'no'} energy, ${d.word}`}>
                <span className={styles.dayName}>{d.shortName}</span>
                <span className={styles.orb} style={{ width: size, height: size, opacity: 0.45 + intensity * 0.55 }} aria-hidden />
                <span className={styles.word}>{d.word}</span>
              </li>
            );
          })}
        </ol>
      </Section>

      <div className={styles.columns}>
        <Section title="Three themes">
          <ol className={styles.themes}>{data.themes.map((t, i) => <li key={i}>{t}</li>)}</ol>
        </Section>
        <Section title="Looking ahead">
          <dl className={styles.ahead}>
            {data.lookahead.map((l, i) => (
              <div key={i}><dt>{l.when}</dt><dd>{l.what}</dd></div>
            ))}
          </dl>
        </Section>
      </div>
    </Page>
  );
}

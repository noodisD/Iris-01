import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { useAllHabits } from '@/hooks/useHabits';
import { LoadingState, ErrorState } from '@/components/states';
import { Calendar, EditHabit, PERIODS } from '@/components/HabitParts';
import { Page } from '@/ui';
import styles from '@/components/HabitParts.module.css';

/** A habit on a page of its own: the same pieces the list opens in place. */
export function HabitDetailScreen() {
  const { period, id } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = useAllHabits();
  if (isLoading) return <LoadingState label="Opening the habit…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;
  const habit = data.find(h => h.id === id);
  if (!habit) return <Navigate to={`/habits/${period ?? 'daily'}`} replace />;
  const frequency = habit.frequency ?? 'daily';
  const p = PERIODS.find(x => x.value === frequency)!;
  const streak = `${habit.streakDays} ${habit.streakUnit ?? 'day'}${habit.streakDays === 1 ? '' : 's'} in a row, best ${habit.bestStreak}`;
  return (
    <Page title={habit.name}
      description={frequency === 'daily' ? streak : `${habit.periodDone ?? 0} of ${habit.target ?? 1} ${p.adverb} · ${streak}`}
      actions={<Link to={`/habits/${frequency}`}>All {p.label.toLowerCase()} habits</Link>}>
      {habit.archived && <p className={styles.warn}>Archived: hidden from your lists, history kept.</p>}
      <Calendar habit={habit} />
      <EditHabit key={habit.id + (habit.frequency ?? '')} habit={habit}
        onSaved={h => navigate(`/habits/${h.frequency ?? 'daily'}/${h.id}`, { replace: true })}
        onDeleted={() => navigate(`/habits/${frequency}`)} />
    </Page>
  );
}

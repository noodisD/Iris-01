import { Navigate, Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { PhoneNav } from './PhoneNav';
import styles from './AppLayout.module.css';
import { LoadingState } from './states';
import { useOnboarding } from '@/hooks/useData';

/**
 * App shell. Also the first-run gate: the backend tracks onboarding state, and
 * until it reports `done` the app sends you to /onboarding. Without this the
 * onboarding API had no consumer and the first-run flow was decorative.
 */
export function AppLayout() {
  const { data: onboarding, isLoading } = useOnboarding();

  if (isLoading) return <LoadingState label="Waking Iris…" />;
  if (onboarding && onboarding.step !== 'done') return <Navigate to="/onboarding" replace />;

  return (
    <div className={styles.shell}>
      <div className={styles.desktopNav}><Sidebar /></div>
      <main className={styles.main}>
        <Outlet />
      </main>
      <PhoneNav />
    </div>
  );
}

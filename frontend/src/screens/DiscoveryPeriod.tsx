import { Link, useSearchParams } from 'react-router-dom';
import type { DiscoveryRange } from '@/types/api';

export function useDiscoveryPeriod(): [DiscoveryRange | null, (period: DiscoveryRange) => void] {
  const [params, setParams] = useSearchParams();
  const requested = params.get('range') ?? 'all';
  const period = requested === 'all' || requested === '30d' || requested === '90d' ? requested : null;
  return [period, next => {
    setParams(previous => {
      const updated = new URLSearchParams(previous);
      updated.set('range', next);
      return updated;
    }, { replace: true });
  }];
}

export function DiscoveryPeriod({ period, onChange }: {
  period: DiscoveryRange; onChange: (period: DiscoveryRange) => void;
}) {
  return <label>Writing recorded in{' '}
    <select aria-label="Writing period" value={period} onChange={event => onChange(event.target.value as DiscoveryRange)}>
      <option value="all">All available writing</option>
      <option value="30d">Last 30 days</option>
      <option value="90d">Last 90 days</option>
    </select>
  </label>;
}

export function InvalidDiscoveryPeriod() {
  return <p role="alert">Unknown writing period. <Link to="?range=all" replace>All available writing</Link></p>;
}

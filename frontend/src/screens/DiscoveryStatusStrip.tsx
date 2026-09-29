import { useDiscoveryRefresh, useDiscoveryStatus } from '@/hooks/usePatterns';
import { Button } from '@/ui';

/** Reading the existing archive is explicit; new writing is queued independently. */
export function DiscoveryStatusStrip() {
  const status = useDiscoveryStatus();
  const refresh = useDiscoveryRefresh();
  if (status.isPending) return <p role="status">Checking reading status…</p>;
  if (status.isError || !status.data) {
    return <p role="alert">Reading status unavailable. <Button size="sm" onClick={() => status.refetch()}>Retry</Button></p>;
  }
  const s = status.data;
  return (
    <section aria-label="Reading status">
      <p>{s.currentEntries} of {s.eligibleEntries} eligible entries read · {s.pendingEntries} pending · {s.failedEntries} could not be read.
        {s.lastCompletedAt && <> Last completed {new Date(s.lastCompletedAt).toLocaleString()}.</>}
      </p>
      {s.omittedAccounts > 0 && <p>{s.omittedAccounts} accounts could not be supported by their cited writing.</p>}
      {s.unreadEntries > 0 && <>
        <p>Read existing writing with {s.model}: {s.estimatedRequests} estimated requests. {s.estimate} This reading may yield fewer accounts than older readings.</p>
        <Button size="sm" disabled={refresh.isPending} onClick={() => refresh.mutate('unread')}>Read existing writing</Button>
      </>}
      {s.failedEntries > 0 && <Button size="sm" disabled={refresh.isPending} onClick={() => refresh.mutate('failed')}>Retry failed reading</Button>}
      {refresh.isError && <p role="alert">The reading request did not start. Try again.</p>}
    </section>
  );
}

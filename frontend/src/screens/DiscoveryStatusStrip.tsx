import { useDiscoveryRefresh, useDiscoveryStatus } from '@/hooks/usePatterns';
import { Button } from '@/ui';

/** Archive reading is explicit; new eligible writing queues automatically. */
export function DiscoveryStatusStrip() {
  const status = useDiscoveryStatus();
  const refresh = useDiscoveryRefresh();
  if (status.isPending) return <p role="status">Checking reading status…</p>;
  if (status.isError || !status.data) {
    return <p role="alert">Reading status unavailable. <Button size="sm" onClick={() => status.refetch()}>Retry</Button></p>;
  }
  const s = status.data;
  const estimate = s.estimate;
  return <section aria-label="Discovery status">
    <p role="status">{s.stage === 'ready' ? 'Personal discovery ready' : `Personal discovery ${s.stage}`} ·
      {' '}{s.currentEntries} of {s.eligibleEntries} eligible entries read · {s.pendingEntries} pending ·
      {' '}{s.failedEntries} failed · {s.synthesisPending ? 'synthesis pending' : s.synthesisFailed ? 'synthesis failed' : 'synthesis not pending'}.
      {s.lastCompletedAt && <> Last completed {new Date(s.lastCompletedAt).toLocaleString()}.</>}
    </p>
    {(s.omittedAccounts > 0 || s.omittedFields > 0) && <p>{s.omittedAccounts} accounts omitted ·
      {' '}{s.omittedFields} unsupported fields omitted. These are separate from missing pattern matches.</p>}
    {(s.unreadEntries > 0 || s.failedEntries > 0 || s.synthesisFailed || s.stage !== 'ready') && <>
      <p>Estimated archive work with {s.model}: {estimate.readingRequests} reading requests,
        {' '}{estimate.synthesisRequests} synthesis requests; approximately {estimate.tokensIn} input and
        {' '}{estimate.tokensOut} output tokens ({estimate.costText}). Estimate only; reading may find no qualifying dynamics.</p>
      {(s.unreadEntries > 0 || s.stage !== 'ready' && !s.synthesisPending && !s.synthesisFailed) &&
        <Button size="sm" disabled={refresh.isPending} onClick={() => refresh.mutate('unread')}>Read existing writing</Button>}
      {(s.failedEntries > 0 || s.synthesisFailed) &&
        <Button size="sm" disabled={refresh.isPending} onClick={() => refresh.mutate('failed')}>Retry failed work</Button>}
    </>}
    {refresh.isError && <p role="alert">The discovery request did not start. Try again.</p>}
  </section>;
}

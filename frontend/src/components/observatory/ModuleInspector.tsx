import type { ObsModuleCalls, ObsModuleEdge, ObsModuleNode, ObsSpanSummary } from '@/api/observatory';
import type { ObsInvocationDetail } from '@/api/observatory';
import { ArrowLeft, X } from 'lucide-react';
import { ErrorState, LoadingState } from '@/components/states';
import { ago, ms } from '@/lib/obsFormat';
import { Badge, Button, IconButton, Tabs, TabPanel } from '@/ui';
import { InvocationDetail } from './InvocationDetail';
import styles from './ModuleInspector.module.css';

export type InspectorTab = 'invocation' | 'module' | 'calls';

const KIND_TEXT: Record<ObsModuleEdge['kind'], string> = {
  call: 'Call',
  flow: 'Declared data flow',
  causal: 'Queued from',
};

export function ModuleInspector({
  node, missing, edges, calls, callsLoading, callsError, onRetryCalls,
  invocation, selectedCall, invocationError, onRetryInvocation,
  followLatest, onFollowLatest, onSelectCall, onLatest, onFollowTrace,
  tab, onTabChange, onClose, onBack,
}: {
  node: ObsModuleNode | null;
  missing: boolean;
  edges: ObsModuleEdge[];
  calls: ObsModuleCalls | undefined;
  callsLoading: boolean;
  callsError?: string;
  onRetryCalls?: () => void;
  invocation: ObsInvocationDetail | undefined;
  selectedCall: boolean;
  invocationError?: string;
  onRetryInvocation?: () => void;
  followLatest: boolean;
  onFollowLatest: (value: boolean) => void;
  onSelectCall: (span: ObsSpanSummary) => void;
  onLatest: () => void;
  onFollowTrace: () => void;
  tab: InspectorTab;
  onTabChange: (tab: InspectorTab) => void;
  onClose: () => void;
  onBack: () => void;
}) {
  const errors = node?.stats?.errors ?? 0;
  return (
    <div className={styles.inspector}>
      <header className={styles.header}>
        <Button variant="quiet" size="sm" className={styles.backButton} onClick={onBack}>
          <ArrowLeft />Back to map
        </Button>
        <h2 className={styles.title} tabIndex={-1}>{node ? node.label : 'Inspector'}</h2>
        {node && <span className={styles.idText}>{node.id}</span>}
        {node && node.active > 0 && <Badge tone="action">Running {node.active}</Badge>}
        {node && node.active === 0 && errors > 0 && <Badge tone="worse">{errors} errors</Badge>}
        <IconButton label="Close inspector" icon={<X />} onClick={onClose} />
      </header>
      {!node && missing && <p role="status" className={styles.stateMessage}>This module is not in the current map.</p>}
      {!node && !missing && <div className={styles.stateBody}><LoadingState label="Loading the module…" /></div>}
      {node && node.id === 'android.collector.state' && (
        <div className={styles.stateBody}>
          <p>Snapshot; not a timed invocation.</p>
          <p>Received {node.latest_state ? ago(node.latest_state.received_at) : '—'}</p>
          <p className={styles.wrap}>{JSON.stringify(node.latest_state?.value ?? null, null, 2)}</p>
        </div>
      )}
      {node && node.id !== 'android.collector.state' && (
        <Tabs label="Module inspector" value={tab} onChange={onTabChange} tabs={[
          { value: 'invocation', label: 'Invocation' },
          { value: 'module', label: 'Module' },
          { value: 'calls', label: 'Calls' },
        ]}>
          <TabPanel value="invocation">
            <div className={styles.tabBody}>
              <div className={styles.actions}>
                <Button size="sm" onClick={onLatest} disabled={!calls || (calls.active.length === 0 && calls.recent.length === 0)}>Latest call</Button>
                <Button size="sm" onClick={() => onFollowLatest(!followLatest)}>{followLatest ? 'Following latest' : 'Follow latest'}</Button>
                <Button size="sm" onClick={onFollowTrace} disabled={!selectedCall}>Follow this trace</Button>
              </div>
              {!selectedCall && (
                <>
                  {callsError && <ErrorState message={callsError} onRetry={onRetryCalls} />}
                  {!callsError && callsLoading && <LoadingState label="Loading calls…" />}
                  {!callsError && !callsLoading && calls && (calls.active.length > 0 || calls.recent.length > 0) && (
                    <LoadingState label="Selecting the latest call…" />
                  )}
                  {!callsError && !callsLoading && calls && calls.active.length === 0 && calls.recent.length === 0 && (
                    <p className={styles.stateMessage}>No recorded call in this window.</p>
                  )}
                </>
              )}
              {selectedCall && (
                <>
                  {invocation && (
                    <p className={styles.callSummary}>
                      <Badge tone={invocation.span.status === 'running' ? 'action' : invocation.span.status === 'error' ? 'worse' : 'neutral'}>
                        {invocation.span.status === 'running' ? 'Running' : invocation.span.status === 'error' ? 'Error' : 'OK'}
                      </Badge>{' '}
                      Started {new Date(invocation.span.started_at).toLocaleString()},{' '}
                      {invocation.span.status === 'running' ? 'Running' : ms(invocation.span.duration_ms)},{' '}
                      trace {invocation.span.trace_id.slice(0, 8)}
                    </p>
                  )}
                  <InvocationDetail
                    detail={invocation}
                    error={invocationError}
                    onRetry={onRetryInvocation}
                    onSelect={(nextTrace, nextSpan) => {
                      const related = invocation?.related.find(span => span.trace_id === nextTrace && span.span_id === nextSpan);
                      if (related) onSelectCall(related);
                    }}
                  />
                </>
              )}
            </div>
          </TabPanel>
          <TabPanel value="module">
            <div className={styles.tabBody}>
              <h3 className={styles.sectionTitle}>Declared interface</h3>
              <dl className={styles.facts}>
                <div className={styles.fact}><dt>In</dt><dd>{node.inputs.join(', ') || '—'}</dd></div>
                <div className={styles.fact}><dt>Out</dt><dd>{node.outputs.join(', ') || '—'}</dd></div>
                {node.source && (
                  <div className={styles.fact}>
                    <dt>Source</dt>
                    <dd>{node.source.file} {node.source.symbol}{node.source.line != null ? `:${node.source.line}` : ''}</dd>
                  </div>
                )}
                {node.signature && (
                  <div className={styles.fact}><dt>Signature</dt><dd className={styles.wrap}>{node.signature}</dd></div>
                )}
              </dl>
              <h3 className={styles.sectionTitle}>This window</h3>
              {node.stats ? (
                <p>
                  {node.stats.calls} calls, {node.stats.errors} errors, p50 {ms(node.stats.p50_ms)}, p95 {ms(node.stats.p95_ms)}, {node.stats.rate_per_min == null ? '—' : Math.round(node.stats.rate_per_min * 10) / 10} per minute, last seen {ago(node.stats.last_seen)}
                </p>
              ) : (
                <p className={styles.stateMessage}>Not observed in this window.</p>
              )}
              <p>Active {node.active}</p>
              <h3 className={styles.sectionTitle}>Callers</h3>
              {edges.filter(edge => edge.target === node.id).length === 0
                ? <p className={styles.stateMessage}>None.</p>
                : (
                  <ul className={styles.edgeList}>
                    {edges.filter(edge => edge.target === node.id).map(edge => (
                      <li key={`${edge.source}|${edge.kind}`}>{edge.source}, {KIND_TEXT[edge.kind]}, {edge.evidence}, {edge.calls ?? 'no measured'} calls</li>
                    ))}
                  </ul>
                )}
              <h3 className={styles.sectionTitle}>Callees</h3>
              {edges.filter(edge => edge.source === node.id).length === 0
                ? <p className={styles.stateMessage}>None.</p>
                : (
                  <ul className={styles.edgeList}>
                    {edges.filter(edge => edge.source === node.id).map(edge => (
                      <li key={`${edge.target}|${edge.kind}`}>{edge.target}, {KIND_TEXT[edge.kind]}, {edge.evidence}, {edge.calls ?? 'no measured'} calls</li>
                    ))}
                  </ul>
                )}
            </div>
          </TabPanel>
          <TabPanel value="calls">
            <div className={styles.tabBody}>
              {callsError && <ErrorState message={callsError} onRetry={onRetryCalls} />}
              {!callsError && callsLoading && <LoadingState label="Loading calls…" />}
              {!callsError && !callsLoading && (
                <>
                  <h3 className={styles.sectionTitle}>Running</h3>
                  {(calls?.active ?? []).length === 0
                    ? <p className={styles.stateMessage}>None running.</p>
                    : (
                      <ul className={styles.callList}>
                        {(calls?.active ?? []).map(span => <CallRow key={`${span.trace_id}:${span.span_id}`} span={span} onSelect={onSelectCall} />)}
                      </ul>
                    )}
                  <h3 className={styles.sectionTitle}>Completed</h3>
                  {(calls?.recent ?? []).slice(0, 50).length === 0
                    ? <p className={styles.stateMessage}>No completed calls in this window.</p>
                    : (
                      <ul className={styles.callList}>
                        {(calls?.recent ?? []).slice(0, 50).map(span => <CallRow key={`${span.trace_id}:${span.span_id}`} span={span} onSelect={onSelectCall} />)}
                      </ul>
                    )}
                </>
              )}
            </div>
          </TabPanel>
        </Tabs>
      )}
    </div>
  );
}

function CallRow({ span, onSelect }: { span: ObsSpanSummary; onSelect: (span: ObsSpanSummary) => void }) {
  return (
    <li>
      <button type="button" className={styles.callRow} onClick={() => onSelect(span)}>
        <Badge tone={span.status === 'running' ? 'action' : span.status === 'error' ? 'worse' : 'neutral'}>
          {span.status === 'running' ? 'Running' : span.status === 'error' ? 'Error' : 'OK'}
        </Badge>
        <span className={styles.callName}>{span.name}</span>
        <span className={styles.callCell}>{new Date(span.started_at).toLocaleTimeString()}</span>
        <span className={styles.callCell}>{span.status === 'running' ? 'Running' : ms(span.duration_ms)}</span>
        <span className={styles.callCell}>{span.trace_id.slice(0, 8)}</span>
      </button>
    </li>
  );
}

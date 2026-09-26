import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useSensorBatches, useSensorBatch, useSensorActions } from '@/hooks/useSensors';
import { useKnowledge } from '@/hooks/useData';
import { DayGrounding } from '@/components/sensors/DayGrounding';
import { LoadingState, ErrorState, EmptyState } from '@/components/states';
import type { SensorBatch, SensorObservation } from '@/api/sensors';
import { HttpError } from '@/api/client';

const PAGE_SIZE = 100;
const unitBySource: Record<string, string> = {
  pixel_steps: 'steps',
  pixel_app_usage: 'seconds foreground',
  health_connect_heart_rate: 'bpm',
  health_connect_sleep: 'minutes asleep',
  health_connect_spo2: '%',
};

const sourceLabel = (source: string) =>
  source === 'pixel' ? 'Pixel' : source === 'health_connect' ? 'Health Connect' : source === 'google_timeline' ? 'Timeline' : source;

export function SensorsScreen() {
  const { data: batches, isLoading, error, refetch } = useSensorBatches();
  const [selectedId, setSelectedId] = useState<number>();

  return (
    <div className="col" style={{ height: '100%', overflow: 'hidden' }}>
      <header className="col" style={{ padding: '28px 40px 22px', gap: 12, borderBottom: '1px solid var(--line)' }}>
        <div className="kicker">sensors · review before linking</div>
        <h1 className="serif" style={{ margin: 0, fontSize: 38 }}>Your measurements</h1>
        <p style={{ margin: 0, maxWidth: 580, fontSize: 13, lineHeight: 1.5, color: 'var(--ink-2)' }}>
          Readings arrive as one batch per source per day. Review a day&apos;s batch before linking
          any measurements to a theme. <Link to="/settings">Pair the phone in Settings</Link>.
        </p>
      </header>
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <nav aria-label="Sensor batches" style={{ width: 280, borderRight: '1px solid var(--line-soft)', overflowY: 'auto', flexShrink: 0 }}>
          <div className="kicker" style={{ padding: '20px 22px 12px' }}>staged batches</div>
          {isLoading ? <LoadingState label="Loading sensor batches…" /> : error ? (
            <ErrorState message={error instanceof Error ? error.message : String(error)} onRetry={() => refetch()} />
          ) : !batches?.length ? (
            <EmptyState title="No sensor data" body="Pair the Android app and start live collection; new readings will appear here." />
          ) : batches.map((batch) => (
            <button
              key={batch.id} type="button" aria-pressed={batch.id === selectedId}
              onClick={() => setSelectedId(batch.id)}
              style={{
                display: 'block', width: '100%', padding: '12px 22px', textAlign: 'left',
                cursor: 'pointer', border: 'none', borderBottom: '1px solid var(--line-soft)',
                background: batch.id === selectedId ? 'var(--bg-2)' : 'transparent',
              }}
            >
              <span style={{ display: 'block', fontSize: 14, color: 'var(--ink)' }}>
                {sourceLabel(batch.source)} · {batch.review_day ?? new Date(batch.received_at).toLocaleDateString()}
              </span>
              <span style={{ display: 'block', fontSize: 11, color: 'var(--ink-3)', marginTop: 4 }}>
                {batch.status} · {batch.observation_count} readings
                {batch.last_delivery_at && ` · last delivery ${new Date(batch.last_delivery_at).toLocaleTimeString()}`}
              </span>
            </button>
          ))}
        </nav>
        <main style={{ flex: 1, minWidth: 0, overflowY: 'auto' }}>
          {selectedId != null ? (
            <BatchDetail
              key={selectedId} batchId={selectedId} onDeleted={() => setSelectedId(undefined)}
              batches={batches ?? []}
            />
          ) : (
            <DayGrounding onBatchesChanged={() => { void refetch(); }} />
          )}
        </main>
      </div>
    </div>
  );
}

function BatchDetail({ batchId, onDeleted, batches }: { batchId: number; onDeleted: () => void; batches: SensorBatch[] }) {
  const { data: batch, isLoading, error, refetch } = useSensorBatch(batchId);

  if (isLoading) return <LoadingState label="Loading measurements…" />;
  if (error) return <ErrorState message={error instanceof Error ? error.message : String(error)} onRetry={() => refetch()} />;
  if (!batch) return <EmptyState title="Batch unavailable" body="Select another batch or try again." />;
  const suggestedLinks = batches.find((previous) =>
    previous.source === batch.source && previous.status === 'confirmed')?.theme_links ?? {};
  return <BatchReview key={batch.id} batch={batch} onDeleted={onDeleted}
    suggestedLinks={suggestedLinks} refetchBatch={() => { void refetch(); }} />;
}

function BatchReview({ batch, onDeleted, suggestedLinks, refetchBatch }: {
  batch: SensorBatch; onDeleted: () => void; suggestedLinks: Record<string, number | null>;
  refetchBatch: () => void;
}) {
  const { data: knowledge, isLoading: themesLoading, error: themesError, refetch: refetchThemes } = useKnowledge();
  const { confirm, reject, discard } = useSensorActions(batch.id);
  const [links, setLinks] = useState<Record<string, number | null>>(() => {
    if (Object.keys(batch.theme_links ?? {}).length) return batch.theme_links;
    const types = new Set(batch.parsed_payload?.observations.map((obs) => obs.source_type) ?? []);
    return Object.fromEntries(Object.entries(suggestedLinks).filter(([source]) => types.has(source)));
  });
  const [visibleCounts, setVisibleCounts] = useState<Record<string, number>>({});
  const [stale, setStale] = useState(false);
  const { groups, undatedCount } = useMemo(() => {
    const grouped = new Map<string, SensorObservation[]>();
    let undatedCount = 0;
    for (const reading of batch.parsed_payload?.observations ?? []) {
      const readings = grouped.get(reading.source_type) ?? [];
      readings.push(reading);
      grouped.set(reading.source_type, readings);
      if (!reading.occurred_at || !Number.isFinite(Date.parse(reading.occurred_at))) undatedCount++;
    }
    return { groups: Array.from(grouped), undatedCount };
  }, [batch.parsed_payload]);
  const themeIds = new Set((knowledge ?? []).map((theme) => Number(theme.id)));
  const busy = confirm.isPending || reject.isPending || discard.isPending;
  const actionError = confirm.error ?? reject.error ?? discard.error;

  const clearActionErrors = () => {
    confirm.reset();
    reject.reset();
    discard.reset();
  };

  return (
    <section className="col" style={{ padding: '32px 40px 48px', gap: 26, maxWidth: 840 }}>
      <div className="col" style={{ gap: 6 }}>
        <h2 className="serif" style={{ fontSize: 28, margin: 0 }}>Review {sourceLabel(batch.source)} readings</h2>
        <div style={{ color: 'var(--ink-3)', fontSize: 12 }}>
          Received {new Date(batch.received_at).toLocaleString()} · {batch.observation_count} readings · {batch.dropped_count} dropped
        </div>
      </div>
      {batch.status === 'pending' && !Object.keys(batch.theme_links ?? {}).length &&
        Object.keys(links).length > 0 && (
          <div role="note" style={{ color: 'var(--ink-2)', fontSize: 12 }}>
            Links prefilled from your last confirmed {sourceLabel(batch.source)} batch.
          </div>
        )}

      {batch.status !== 'pending' && (
        <div role="status" style={{ padding: 14, background: 'var(--bg-2)', borderRadius: 8, color: 'var(--ink-2)' }}>
          This batch is <strong>{batch.status}</strong>.
        </div>
      )}
      {batch.dropped_count > 0 && (
        <div role="note" style={{ padding: '11px 14px', border: '1px solid var(--amber)', borderRadius: 8, fontSize: 12 }}>
          {batch.dropped_count} readings were dropped while parsing this batch.
        </div>
      )}
      {undatedCount > 0 && (
        <div role="note" style={{ padding: '11px 14px', border: '1px solid var(--amber)', borderRadius: 8, fontSize: 12 }}>
          {undatedCount} {undatedCount === 1 ? 'reading has' : 'readings have'} no readable date. Check these before linking.
        </div>
      )}
      {batch.clock_skew_seconds != null && Math.abs(batch.clock_skew_seconds) >= 120 && (
        <div role="note" style={{ padding: '11px 14px', border: '1px solid var(--amber)', borderRadius: 8, fontSize: 12 }}>
          Device clock skew detected: {batch.clock_skew_seconds > 0 ? '+' : ''}{batch.clock_skew_seconds} seconds. Check reading times against your device.
        </div>
      )}

      <div className="col" style={{ gap: 16 }}>
        <div className="kicker">observations by source</div>
        {themesLoading && <div role="status" style={{ fontSize: 12, color: 'var(--ink-3)' }}>Loading existing themes…</div>}
        {themesError && (
          <div role="alert" style={{ fontSize: 12, color: 'var(--rose)' }}>
            Could not load themes: {themesError instanceof Error ? themesError.message : String(themesError)}
            {' '}<button className="btn ghost" onClick={() => refetchThemes()}>Try again</button>
          </div>
        )}
        {groups.length === 0 && <EmptyState title="No readable measurements" body="This batch has no observations to link." />}
        {groups.map(([sourceType, readings], index) => {
          const selectedTheme = batch.status === 'pending' ? links[sourceType] : batch.theme_links?.[sourceType];
          const validTheme = selectedTheme != null && themeIds.has(selectedTheme);
          return (
            <section key={sourceType} className="col" style={{ gap: 14, border: '1px solid var(--line-soft)', padding: '16px 20px', borderRadius: 8 }}>
              <div style={{ fontSize: 14, color: 'var(--ink)' }}>
                <strong>{sourceType}</strong> <span style={{ color: 'var(--ink-3)' }}>({readings.length} readings)</span>
              </div>
              <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                {readings.slice(0, visibleCounts[sourceType] ?? PAGE_SIZE).map((reading, readingIndex) => {
                  const date = new Date(reading.occurred_at ?? '');
                  const readableDate = !!reading.occurred_at && Number.isFinite(date.getTime());
                  const calendarDay = /^\d{4}-\d{2}-\d{2}$/.test(reading.occurred_at ?? '');
                  const unit = unitBySource[sourceType];
                  const numeric = reading.value_num == null ? null :
                    `${reading.value_num}${unit === '%' ? '%' : unit ? ` ${unit}` : ''}`;
                  const location = reading.lat != null || reading.lon != null ?
                    `latitude ${reading.lat ?? 'unknown'}, longitude ${reading.lon ?? 'unknown'}` : null;
                  const values = [numeric, reading.value_text || null, location,
                    reading.origin_package ? `Health Connect writer: ${reading.origin_package}` : null].filter(Boolean);
                  return (
                    <li key={`${reading.payload_hash}-${readingIndex}`} className="row" style={{
                      justifyContent: 'space-between', gap: 16, padding: '9px 0',
                      borderTop: '1px solid var(--line-soft)', fontSize: 13, flexWrap: 'wrap',
                    }}>
                      <span style={{ color: 'var(--ink)' }}>{values.length ? values.join(' · ') : 'No value recorded'}</span>
                      <time dateTime={reading.occurred_at && readableDate ? reading.occurred_at : undefined} style={{ color: readableDate ? 'var(--ink-3)' : 'var(--amber)', fontSize: 12 }}>
                        {readableDate ? (calendarDay ? reading.occurred_at : date.toLocaleString()) : 'No readable date'}
                      </time>
                    </li>
                  );
                })}
              </ul>
              {(visibleCounts[sourceType] ?? PAGE_SIZE) < readings.length && (
                <button className="btn ghost" type="button" onClick={() => setVisibleCounts((previous) => ({
                  ...previous, [sourceType]: (previous[sourceType] ?? PAGE_SIZE) + PAGE_SIZE,
                }))} style={{ alignSelf: 'flex-start', fontSize: 12 }}>
                  Show more {sourceType} readings ({readings.length - (visibleCounts[sourceType] ?? PAGE_SIZE)} remaining)
                </button>
              )}
              <div className="col" style={{ gap: 6 }}>
                <label htmlFor={`sensor-link-${batch.id}-${index}`} style={{ fontSize: 12, color: 'var(--ink-2)' }}>
                  Link {sourceType} to an existing theme
                </label>
                <select
                  id={`sensor-link-${batch.id}-${index}`}
                  value={validTheme ? selectedTheme : ''}
                  onChange={(e) => setLinks((previous) => ({ ...previous, [sourceType]: e.target.value ? Number(e.target.value) : null }))}
                  disabled={batch.status !== 'pending' || busy || themesLoading || !!themesError}
                  style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid var(--line-soft)', background: 'var(--bg-1)', color: 'var(--ink)', fontSize: 13 }}
                >
                  <option value="">Do not link — keep raw reading, not evidence</option>
                  {(knowledge ?? []).map((theme) => <option key={theme.id} value={theme.id}>{theme.fact}</option>)}
                </select>
                {!themesLoading && !themesError && knowledge?.length === 0 && (
                  <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>No themes yet. These readings can still be kept unlinked.</span>
                )}
              </div>
            </section>
          );
        })}
      </div>

      {stale && <div role="alert" style={{ color: 'var(--amber)', fontSize: 12 }}>
        New readings arrived while you were reviewing. Check them, then confirm again.
      </div>}
      {actionError && (
        <div role="alert" style={{ padding: '11px 14px', border: '1px solid var(--rose)', borderRadius: 8, color: 'var(--rose)', fontSize: 12 }}>
          Request failed: {actionError instanceof Error ? actionError.message : String(actionError)}
        </div>
      )}
      <div className="row" style={{ gap: 12, flexWrap: 'wrap', paddingTop: 16, borderTop: '1px solid var(--line-soft)' }}>
        {batch.status === 'pending' && (
          <>
            <button className="btn primary" disabled={busy || themesLoading || !!themesError} onClick={() => {
              clearActionErrors();
              confirm.mutate({
                links: Object.fromEntries(groups.map(([sourceType]) => [sourceType,
                  themeIds.has(links[sourceType] ?? NaN) ? links[sourceType] : null])),
                observationCount: batch.observation_count,
              }, {
                onError: (error) => {
                  if (error instanceof HttpError && error.status === 409) {
                    setStale(true);
                    refetchBatch();
                  }
                },
                onSuccess: () => setStale(false),
              });
            }}>
              {confirm.isPending ? 'Confirming…' : 'Confirm & link selected themes'}
            </button>
            <button className="btn" disabled={busy} onClick={() => { clearActionErrors(); reject.mutate(); }}>
              {reject.isPending ? 'Rejecting…' : 'Reject data'}
            </button>
          </>
        )}
        <button className="btn ghost" disabled={busy} onClick={() => {
          clearActionErrors();
          discard.mutate(undefined, { onSuccess: onDeleted });
        }} style={{ marginLeft: 'auto', color: 'var(--rose)' }}>
          {discard.isPending ? 'Deleting…' : 'Delete batch'}
        </button>
      </div>
    </section>
  );
}

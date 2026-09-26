import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useSensorBatches, useSensorBatch, useSensorActions } from '@/hooks/useSensors';
import { useKnowledge } from '@/hooks/useData';
import { AppCategories, DaysTable, Location } from '@/components/sensors/DayGrounding';
import { LoadingState, ErrorState, EmptyState } from '@/components/states';
import type { SensorBatch, SensorObservation } from '@/api/sensors';
import { HttpError } from '@/api/client';
import { Badge, Button, Field, Page, Panel, Tabs, TabPanel } from '@/ui';
import styles from './SensorsScreen.module.css';

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

const batchDay = (batch: SensorBatch) => batch.review_day ?? new Date(batch.received_at).toLocaleDateString();

type View = 'days' | 'review' | 'location' | 'apps';
const VIEWS: View[] = ['days', 'review', 'location', 'apps'];

export function SensorsScreen() {
  const { data: batches, isLoading, error, refetch } = useSensorBatches();
  const [params, setParams] = useSearchParams();
  const view = VIEWS.find(v => v === params.get('view')) ?? 'days';
  const pending = (batches ?? []).filter(b => b.status === 'pending').length;

  return (
    <Page title="Sensors" width="wide"
      description={<>What the phone and Google Timeline measured. New readings wait here for your review before IRIS
        uses them. <Link to="/settings">Pair the phone in Settings</Link>.</>}>
      <Tabs label="Sensors" value={view} onChange={next => setParams(next === 'days' ? {} : { view: next })}
        tabs={[
          { value: 'days', label: 'Days' },
          { value: 'review', label: pending ? `To review (${pending})` : 'To review' },
          { value: 'location', label: 'Location' },
          { value: 'apps', label: 'Apps' },
        ]}>
        <TabPanel value="days"><DaysTable /></TabPanel>
        <TabPanel value="review">
          {isLoading ? <LoadingState label="Loading sensor batches…" /> : error ? (
            <ErrorState message={error instanceof Error ? error.message : String(error)} onRetry={() => refetch()} />
          ) : !batches?.length ? (
            <EmptyState title="Nothing to review" body="Pair the Android app and start collecting; new readings appear here." />
          ) : <Review batches={batches} />}
        </TabPanel>
        <TabPanel value="location"><Location onBatchesChanged={() => { void refetch(); }} /></TabPanel>
        <TabPanel value="apps"><AppCategories /></TabPanel>
      </Tabs>
    </Page>
  );
}

function Review({ batches }: { batches: SensorBatch[] }) {
  const [selectedId, setSelectedId] = useState<number>();
  return (
    <div className={`${styles.split} ${selectedId != null ? styles.showing : ''}`}>
      <nav aria-label="Sensor batches" className={styles.list}>
        <ul className={styles.items}>
          {batches.map(batch => (
            <li key={batch.id}>
              <button type="button" aria-pressed={batch.id === selectedId} onClick={() => setSelectedId(batch.id)}
                className={styles.item}>
                <span className={styles.itemName}>{sourceLabel(batch.source)}, {batchDay(batch)}</span>
                <span className={styles.itemMeta}>
                  <Badge tone={batch.status === 'pending' ? 'action' : batch.status === 'confirmed' ? 'confirmed' : 'neutral'}>
                    {batch.status}
                  </Badge>
                  {batch.observation_count} readings
                </span>
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <div className={styles.detail}>
        {selectedId != null ? (
          <>
            <Button variant="quiet" size="sm" className={styles.back} onClick={() => setSelectedId(undefined)}>
              ← All batches
            </Button>
            <BatchDetail key={selectedId} batchId={selectedId} onDeleted={() => setSelectedId(undefined)} batches={batches} />
          </>
        ) : <p className={styles.pick}>Pick a batch to see its readings and confirm or reject it.</p>}
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
    <section className={styles.batch} aria-label={`${sourceLabel(batch.source)} readings`}>
      <header className={styles.batchHead}>
        <h2 className={styles.batchTitle}>{sourceLabel(batch.source)}, {batchDay(batch)}</h2>
        <p className={styles.meta}>
          Received {new Date(batch.received_at).toLocaleString()}. {batch.observation_count} readings
          {batch.dropped_count > 0 && `, ${batch.dropped_count} dropped`}.
        </p>
      </header>
      {batch.status === 'pending' && !Object.keys(batch.theme_links ?? {}).length &&
        Object.keys(links).length > 0 && (
          <p role="note" className={styles.meta}>Links prefilled from your last confirmed {sourceLabel(batch.source)} batch.</p>
        )}
      {batch.status !== 'pending' && (
        <p role="status" className={styles.note}>This batch is <strong>{batch.status}</strong>.</p>
      )}
      {batch.dropped_count > 0 && (
        <p role="note" className={styles.warn}>{batch.dropped_count} readings were dropped while parsing this batch.</p>
      )}
      {undatedCount > 0 && (
        <p role="note" className={styles.warn}>
          {undatedCount} {undatedCount === 1 ? 'reading has' : 'readings have'} no readable date. Check these before linking.
        </p>
      )}
      {batch.clock_skew_seconds != null && Math.abs(batch.clock_skew_seconds) >= 120 && (
        <p role="note" className={styles.warn}>
          The phone&apos;s clock was off by {batch.clock_skew_seconds > 0 ? '+' : ''}{batch.clock_skew_seconds} seconds.
          Check reading times against the phone.
        </p>
      )}
      {themesLoading && <p role="status" className={styles.meta}>Loading existing themes…</p>}
      {themesError && (
        <p role="alert" className={styles.error}>
          Could not load themes: {themesError instanceof Error ? themesError.message : String(themesError)}{' '}
          <Button variant="quiet" size="sm" onClick={() => refetchThemes()}>Try again</Button>
        </p>
      )}
      {groups.length === 0 && <EmptyState title="No readable measurements" body="This batch has no observations to link." />}
      {groups.map(([sourceType, readings]) => {
        const selectedTheme = batch.status === 'pending' ? links[sourceType] : batch.theme_links?.[sourceType];
        const validTheme = selectedTheme != null && themeIds.has(selectedTheme);
        const visible = visibleCounts[sourceType] ?? PAGE_SIZE;
        return (
          <Panel as="section" key={sourceType} className={styles.group} aria-label={sourceType}>
            <h3 className={styles.groupTitle}>{sourceType} <span className={styles.meta}>({readings.length} readings)</span></h3>
            <ul className={styles.readings}>
              {readings.slice(0, visible).map((reading, readingIndex) => {
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
                  <li key={`${reading.payload_hash}-${readingIndex}`} className={styles.reading}>
                    <span>{values.length ? values.join('; ') : 'No value recorded'}</span>
                    <time dateTime={reading.occurred_at && readableDate ? reading.occurred_at : undefined}
                      className={readableDate ? styles.time : styles.undated}>
                      {readableDate ? (calendarDay ? reading.occurred_at : date.toLocaleString()) : 'No readable date'}
                    </time>
                  </li>
                );
              })}
            </ul>
            {visible < readings.length && (
              <Button variant="quiet" size="sm" className={styles.more} onClick={() => setVisibleCounts((previous) => ({
                ...previous, [sourceType]: (previous[sourceType] ?? PAGE_SIZE) + PAGE_SIZE,
              }))}>
                Show more {sourceType} readings ({readings.length - visible} remaining)
              </Button>
            )}
            <Field label={`Link ${sourceType} to a theme`}
              hint={!themesLoading && !themesError && knowledge?.length === 0 ? 'No themes yet. These readings can still be kept unlinked.' : undefined}>
              <select value={validTheme ? selectedTheme : ''}
                onChange={(e) => setLinks((previous) => ({ ...previous, [sourceType]: e.target.value ? Number(e.target.value) : null }))}
                disabled={batch.status !== 'pending' || busy || themesLoading || !!themesError}>
                <option value="">Don&apos;t link: keep as a raw reading, not evidence</option>
                {(knowledge ?? []).map((theme) => <option key={theme.id} value={theme.id}>{theme.fact}</option>)}
              </select>
            </Field>
          </Panel>
        );
      })}

      {stale && <p role="alert" className={styles.warn}>New readings arrived while you were reviewing. Check them, then confirm again.</p>}
      {actionError && (
        <p role="alert" className={styles.error}>
          Not saved: {actionError instanceof Error ? actionError.message : String(actionError)}
        </p>
      )}
      <div className={styles.actions}>
        {batch.status === 'pending' && (
          <>
            <Button variant="primary" disabled={busy || themesLoading || !!themesError} onClick={() => {
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
              {confirm.isPending ? 'Confirming…' : 'Confirm readings'}
            </Button>
            <Button disabled={busy} onClick={() => { clearActionErrors(); reject.mutate(); }}>
              {reject.isPending ? 'Rejecting…' : 'Reject readings'}
            </Button>
          </>
        )}
        <Button variant="danger" disabled={busy} className={styles.delete} onClick={() => {
          clearActionErrors();
          discard.mutate(undefined, { onSuccess: onDeleted });
        }}>
          {discard.isPending ? 'Deleting…' : 'Delete batch'}
        </Button>
      </div>
    </section>
  );
}

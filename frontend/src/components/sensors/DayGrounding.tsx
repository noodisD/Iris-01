import React from 'react';
import {
  confirmTimelineRange, createPlace, deletePlace, listCategories, listDays, listPlaces,
  saveCategory, suggestPlaces, updatePlace, uploadTimeline,
  type DayFeature, type Place, type PlaceSuggestions,
} from '@/api/days';
import { HttpError } from '@/api/client';
import { Button, DataTable, Field, Panel, Section } from '@/ui';
import styles from './DayGrounding.module.css';

/** The measured days, the places that name them, and how apps are counted. */

const message = (err: unknown) => (err instanceof Error ? err.message : String(err));

/** Runs an action, reporting its failure instead of throwing. */
function useAction() {
  const [error, setError] = React.useState<string | null>(null);
  const run = async (action: () => Promise<unknown>) => {
    setError(null);
    try { await action(); } catch (err) { setError(message(err)); }
  };
  return { error, setError, run };
}

const hours = (minutes: number | null) => {
  if (minutes == null) return '–';
  const h = Math.floor(minutes / 60), m = Math.round(minutes % 60);
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m`;
};

export function DaysTable() {
  const [days, setDays] = React.useState<DayFeature[] | null>(null);
  const { error, setError } = useAction();
  React.useEffect(() => { listDays().then(body => setDays(body.days)).catch(err => setError(message(err))); }, [setError]);

  return (
    <Section title="Days" description="One row per confirmed day: where you were, how you moved, screen time and sleep.">
      {error && <p role="alert" className={styles.error}>{error}</p>}
      {days && (
        <DataTable label="Days" rows={days} rowKey={d => d.day}
          empty={<p className={styles.muted}>No confirmed days yet. Confirm readings under To review.</p>}
          columns={[
            { key: 'day', header: 'Day', cell: d => d.day },
            { key: 'kind', header: 'Kind', cell: d => d.dayKind },
            { key: 'home', header: 'Home', numeric: true, cell: d => hours(d.homeMinutes) },
            { key: 'office', header: 'Office', numeric: true, cell: d => hours(d.officeMinutes) },
            { key: 'commute', header: 'Commute', numeric: true, cell: d => hours(d.commuteMinutes) },
            { key: 'steps', header: 'Steps', numeric: true, cell: d => d.steps?.toLocaleString() ?? '–' },
            { key: 'screen', header: 'Screen', numeric: true, cell: d => hours(d.screenMinutes) },
            { key: 'sleep', header: 'Sleep', numeric: true, cell: d => hours(d.sleepMinutes) },
            { key: 'coverage', header: 'Location known', numeric: true, cell: d => `${Math.round(d.locationCoverage * 100)}%` },
          ]} />
      )}
    </Section>
  );
}

type Kind = Place['kind'];
const KINDS: Kind[] = ['home', 'office', 'other'];

export function Location({ onBatchesChanged }: { onBatchesChanged: () => void }) {
  const [available, setAvailable] = React.useState<boolean | null>(null);
  const [places, setPlaces] = React.useState<Place[]>([]);
  const [suggestions, setSuggestions] = React.useState<PlaceSuggestions | null>(null);
  const [note, setNote] = React.useState<string | null>(null);
  const [start, setStart] = React.useState('');
  const [end, setEnd] = React.useState('');
  const [draft, setDraft] = React.useState({ name: '', kind: 'home' as Kind, lat: '', lon: '' });
  const [editing, setEditing] = React.useState<Place | null>(null);
  const { error, setError, run } = useAction();

  const reload = React.useCallback(async () => {
    const body = await listPlaces().catch(err => {
      if (err instanceof HttpError && err.status === 404) return null;
      throw err;
    });
    setAvailable(body !== null);
    setPlaces(body?.places ?? []);
    setSuggestions(body ? await suggestPlaces() : null);
  }, []);
  React.useEffect(() => { void reload().catch(err => setError(message(err))); }, [reload, setError]);

  const accept = (which: 'home' | 'office') => run(async () => {
    const point = suggestions?.[which];
    if (!point) return;
    await createPlace({ name: which === 'home' ? 'Home' : 'Office', kind: which, lat: point.lat, lon: point.lon, radiusM: 150, source: 'timeline' });
    await reload();
  });

  if (available === false) {
    return <p className={styles.muted}>Timeline imports and named places are available on the laptop only.</p>;
  }
  return (
    <div className={styles.stack}>
      {error && <p role="alert" className={styles.error}>{error}</p>}
      <Section title="Places"
        description="Named places turn coordinates into time at home, at the office and on the way. Coordinates stay on this laptop.">
        {(suggestions?.home || suggestions?.office) && (
          <div className={styles.row}>
            <span className={styles.muted}>From your Timeline:</span>
            {suggestions?.home && <Button size="sm" onClick={() => void accept('home')}>Add the suggested home</Button>}
            {suggestions?.office && <Button size="sm" onClick={() => void accept('office')}>Add the suggested office</Button>}
          </div>
        )}
        <DataTable label="Places" rows={places} rowKey={p => String(p.id)}
          empty={<p className={styles.muted}>No places yet.</p>}
          columns={[
            { key: 'name', header: 'Name', cell: p => p.name },
            { key: 'kind', header: 'Kind', cell: p => p.kind },
            { key: 'radius', header: 'Radius', numeric: true, cell: p => `${p.radiusM} m` },
            {
              key: 'actions', header: <span className="visually-hidden">Actions</span>, cell: p => (
                <span className={styles.rowActions}>
                  <Button size="sm" variant="quiet" aria-label={`Edit ${p.name}`} onClick={() => setEditing(p)}>Edit</Button>
                  <Button size="sm" variant="quiet" aria-label={`Remove ${p.name}`}
                    onClick={() => void run(async () => { await deletePlace(p.id); await reload(); })}>Remove</Button>
                </span>
              ),
            },
          ]} />
        {editing ? (
          <Panel as="section" aria-label={`Edit ${editing.name}`}>
            <form className={styles.form} onSubmit={event => {
              event.preventDefault();
              void run(async () => { await updatePlace(editing); setEditing(null); await reload(); });
            }}>
              <Field label="Name"><input required value={editing.name} onChange={e => setEditing({ ...editing, name: e.target.value })} /></Field>
              <Field label="Kind">
                <select value={editing.kind} onChange={e => setEditing({ ...editing, kind: e.target.value as Kind })}>
                  {KINDS.map(k => <option key={k} value={k}>{k}</option>)}
                </select>
              </Field>
              <Field label="Latitude"><input type="number" step="any" required value={editing.lat} onChange={e => setEditing({ ...editing, lat: Number(e.target.value) })} /></Field>
              <Field label="Longitude"><input type="number" step="any" required value={editing.lon} onChange={e => setEditing({ ...editing, lon: Number(e.target.value) })} /></Field>
              <Field label="Radius (m)"><input type="number" min="1" required value={editing.radiusM} onChange={e => setEditing({ ...editing, radiusM: Number(e.target.value) })} /></Field>
              <div className={styles.formActions}>
                <Button type="submit" variant="primary">Save changes</Button>
                <Button onClick={() => setEditing(null)}>Cancel</Button>
              </div>
            </form>
          </Panel>
        ) : (
          <form className={styles.form} aria-label="Add a place" onSubmit={event => {
            event.preventDefault();
            void run(async () => {
              await createPlace({ name: draft.name, kind: draft.kind, lat: Number(draft.lat), lon: Number(draft.lon), radiusM: 150 });
              setDraft({ name: '', kind: 'home', lat: '', lon: '' });
              await reload();
            });
          }}>
            <Field label="Name"><input required value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} /></Field>
            <Field label="Kind">
              <select value={draft.kind} onChange={e => setDraft({ ...draft, kind: e.target.value as Kind })}>
                {KINDS.map(k => <option key={k} value={k}>{k}</option>)}
              </select>
            </Field>
            <Field label="Latitude"><input type="number" step="any" required value={draft.lat} onChange={e => setDraft({ ...draft, lat: e.target.value })} /></Field>
            <Field label="Longitude"><input type="number" step="any" required value={draft.lon} onChange={e => setDraft({ ...draft, lon: e.target.value })} /></Field>
            <div className={styles.formActions}><Button type="submit">Add place</Button></div>
          </form>
        )}
      </Section>

      <Section title="Google Timeline"
        description="On the phone: Google Maps, your profile, Settings, Location and privacy, Timeline, then export the Timeline data. Upload that file here.">
        <Field label="Timeline export (JSON)">
          <input className={styles.file} type="file" accept="application/json,.json"
            onChange={event => {
              const file = event.target.files?.[0];
              if (!file) return;
              void run(async () => {
                const result = await uploadTimeline(file);
                setNote(`Staged ${result.observations} readings in ${result.batches.length} days. ${result.dropped} segments dropped.`);
                onBatchesChanged();
              });
            }} />
        </Field>
        {note && <p role="status" className={styles.muted}>{note}</p>}
        <form className={styles.form} aria-label="Confirm a Timeline range" onSubmit={event => {
          event.preventDefault();
          void run(async () => {
            const result = await confirmTimelineRange(start, end);
            setNote(`Confirmed ${result.confirmed.length} Timeline days.`);
            onBatchesChanged();
          });
        }}>
          <Field label="From"><input type="date" required value={start} onChange={e => setStart(e.target.value)} /></Field>
          <Field label="To"><input type="date" required value={end} onChange={e => setEnd(e.target.value)} /></Field>
          <div className={styles.formActions}><Button type="submit">Confirm these days</Button></div>
        </form>
        <p className={styles.muted}>Confirms the Timeline days waiting for review in this range at once, without linking them to themes.</p>
      </Section>
    </div>
  );
}

export function AppCategories() {
  const [categories, setCategories] = React.useState<{ package: string; category: string }[]>([]);
  const [packageName, setPackageName] = React.useState('');
  const [category, setCategory] = React.useState('other');
  const { error, setError, run } = useAction();
  const reload = React.useCallback(async () => setCategories((await listCategories()).categories), []);
  React.useEffect(() => { void reload().catch(err => setError(message(err))); }, [reload, setError]);

  return (
    <Section title="App categories" description="Screen time is split by these categories. Name an app by its package.">
      {error && <p role="alert" className={styles.error}>{error}</p>}
      <form className={styles.form} aria-label="Set an app's category" onSubmit={event => {
        event.preventDefault();
        void run(async () => { await saveCategory(packageName, category); setPackageName(''); await reload(); });
      }}>
        <Field label="Package"><input required value={packageName} placeholder="com.example.app" onChange={e => setPackageName(e.target.value)} /></Field>
        <Field label="Category"><input required value={category} onChange={e => setCategory(e.target.value)} /></Field>
        <div className={styles.formActions}><Button type="submit">Save category</Button></div>
      </form>
      <DataTable label="App categories" rows={categories} rowKey={r => r.package}
        empty={<p className={styles.muted}>No categories set yet.</p>}
        columns={[
          { key: 'package', header: 'Package', cell: r => r.package },
          { key: 'category', header: 'Category', cell: r => r.category },
        ]} />
    </Section>
  );
}

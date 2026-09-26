import React from 'react';
import {
  confirmTimelineRange, createPlace, deletePlace, listCategories, listDays, listPlaces,
  saveCategory, suggestPlaces, updatePlace, uploadTimeline,
  type DayFeature, type Place, type PlaceSuggestions,
} from '@/api/days';
import { HttpError } from '@/api/client';

const fieldStyle: React.CSSProperties = {
  background: 'var(--bg-2)', border: '1px solid var(--line)',
  borderRadius: 6, color: 'var(--ink)', padding: '7px 9px', font: 'inherit',
};

export function DayGrounding({ onBatchesChanged }: { onBatchesChanged: () => void }) {
  const [places, setPlaces] = React.useState<Place[]>([]);
  const [days, setDays] = React.useState<DayFeature[]>([]);
  const [suggestions, setSuggestions] = React.useState<PlaceSuggestions | null>(null);
  const [categories, setCategories] = React.useState<{ package: string; category: string }[]>([]);
  const [placesAvailable, setPlacesAvailable] = React.useState<boolean | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [note, setNote] = React.useState<string | null>(null);
  const [packageName, setPackageName] = React.useState('');
  const [category, setCategory] = React.useState('other');
  const [name, setName] = React.useState('');
  const [kind, setKind] = React.useState<'home' | 'office' | 'other'>('home');
  const [lat, setLat] = React.useState('');
  const [lon, setLon] = React.useState('');
  const [start, setStart] = React.useState('');
  const [end, setEnd] = React.useState('');
  const [editing, setEditing] = React.useState<Place | null>(null);

  const reload = React.useCallback(async () => {
    const [dayBody, categoryBody, placeBody] = await Promise.all([
      listDays(), listCategories(),
      listPlaces().catch(err => {
        if (err instanceof HttpError && err.status === 404) return null;
        throw err;
      }),
    ]);
    setDays(dayBody.days);
    setCategories(categoryBody.categories);
    setPlacesAvailable(placeBody !== null);
    setPlaces(placeBody?.places ?? []);
    setSuggestions(placeBody ? await suggestPlaces() : null);
  }, []);

  React.useEffect(() => { void reload().catch(err => setError(String(err))); }, [reload]);

  const accept = async (which: 'home' | 'office') => {
    const point = suggestions?.[which];
    if (!point) return;
    setError(null);
    try {
      await createPlace({ name: which === 'home' ? 'Home' : 'Office', kind: which, lat: point.lat, lon: point.lon, radiusM: 150, source: 'timeline' });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="col" style={{ padding: '32px 40px 48px', gap: 28, maxWidth: 920 }}>
      {placesAvailable && <section className="col" style={{ gap: 8 }}>
        <div className="kicker">timeline</div>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.5 }}>
          On the phone: Google Maps, profile, Settings, Location &amp; privacy, Timeline, then export the Timeline data.
          Upload that JSON here. Coordinates stay on this laptop.
        </p>
        <input className="sensor-file" aria-label="Timeline export" type="file" accept="application/json,.json"
          onChange={async event => {
            const file = event.target.files?.[0];
            if (!file) return;
            setError(null);
            try {
              const result = await uploadTimeline(file);
              setNote(`Staged ${result.observations} readings in ${result.batches.length} days. ${result.dropped} segments dropped.`);
              onBatchesChanged();
              await reload();
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err));
            }
          }} />
        {note && <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-3)' }}>{note}</div>}
        <form className="row" style={{ gap: 8, flexWrap: 'wrap' }} onSubmit={async event => {
          event.preventDefault();
          setError(null);
          try {
            const result = await confirmTimelineRange(start, end);
            setNote(`Confirmed ${result.confirmed.length} Timeline days.`);
            onBatchesChanged();
            await reload();
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
          }
        }}>
          <label>From <input aria-label="Confirm from" type="date" required style={fieldStyle} value={start} onChange={event => setStart(event.target.value)} /></label>
          <label>To <input aria-label="Confirm to" type="date" required style={fieldStyle} value={end} onChange={event => setEnd(event.target.value)} /></label>
          <button className="btn" type="submit">Confirm Timeline range</button>
        </form>
        <p style={{ margin: 0, fontSize: 12, color: 'var(--ink-3)' }}>
          Only pending Timeline days in this range are confirmed; none are linked to themes.
        </p>
      </section>}
      {placesAvailable === false && <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>
        Timeline imports and named places are available on the laptop only. Days remain visible here.
      </p>}

      {placesAvailable && <section className="col" style={{ gap: 8 }}>
        <div className="kicker">places</div>
        {suggestions?.home && <button className="btn" type="button" onClick={() => void accept('home')}>Accept home suggestion</button>}
        {suggestions?.office && <button className="btn" type="button" onClick={() => void accept('office')}>Accept office suggestion</button>}
        <form className="row" style={{ gap: 8, flexWrap: 'wrap' }} onSubmit={async event => {
          event.preventDefault();
          setError(null);
          try {
            await createPlace({ name, kind, lat: Number(lat), lon: Number(lon), radiusM: 150 });
            setName('');
            await reload();
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
          }
        }}>
          <input aria-label="Place name" style={fieldStyle} required value={name} onChange={event => setName(event.target.value)} placeholder="Name" />
          <select aria-label="Place kind" style={fieldStyle} value={kind} onChange={event => setKind(event.target.value as typeof kind)}>
            <option value="home">home</option>
            <option value="office">office</option>
            <option value="other">other</option>
          </select>
          <input aria-label="Latitude" type="number" step="any" required style={fieldStyle} value={lat} onChange={event => setLat(event.target.value)} />
          <input aria-label="Longitude" type="number" step="any" required style={fieldStyle} value={lon} onChange={event => setLon(event.target.value)} />
          <button className="btn" type="submit">Save place</button>
        </form>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {places.map(place => <li key={place.id}>
            {place.name} · {place.kind}
            {' '}<button className="btn" type="button" onClick={() => setEditing(place)}>Edit</button>
            {' '}<button className="btn" type="button" onClick={async () => {
              setError(null);
              try { await deletePlace(place.id); await reload(); }
              catch (err) { setError(err instanceof Error ? err.message : String(err)); }
            }}>Remove</button>
          </li>)}
        </ul>
        {editing && <form className="row" style={{ gap: 8, flexWrap: 'wrap' }} onSubmit={async event => {
          event.preventDefault();
          setError(null);
          try {
            await updatePlace(editing);
            setEditing(null);
            await reload();
          } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
        }}>
          <input aria-label="Edit place name" style={fieldStyle} required value={editing.name} onChange={event => setEditing({ ...editing, name: event.target.value })} />
          <select aria-label="Edit place kind" style={fieldStyle} value={editing.kind} onChange={event => setEditing({ ...editing, kind: event.target.value as Place['kind'] })}>
            <option value="home">home</option><option value="office">office</option><option value="other">other</option>
          </select>
          <input aria-label="Edit latitude" type="number" step="any" required style={fieldStyle} value={editing.lat} onChange={event => setEditing({ ...editing, lat: Number(event.target.value) })} />
          <input aria-label="Edit longitude" type="number" step="any" required style={fieldStyle} value={editing.lon} onChange={event => setEditing({ ...editing, lon: Number(event.target.value) })} />
          <input aria-label="Edit radius metres" type="number" min="1" required style={fieldStyle} value={editing.radiusM} onChange={event => setEditing({ ...editing, radiusM: Number(event.target.value) })} />
          <button className="btn" type="submit">Save changes</button>
          <button className="btn" type="button" onClick={() => setEditing(null)}>Cancel</button>
        </form>}
      </section>}

      <section className="col" style={{ gap: 8 }}>
        <div className="kicker">app categories</div>
        <form className="row" style={{ gap: 8 }} onSubmit={async event => {
          event.preventDefault();
          setError(null);
          try {
            await saveCategory(packageName, category);
            await reload();
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
          }
        }}>
          <input aria-label="Package" required style={fieldStyle} value={packageName} onChange={event => setPackageName(event.target.value)} />
          <input aria-label="Category" required style={fieldStyle} value={category} onChange={event => setCategory(event.target.value)} />
          <button className="btn" type="submit">Save category</button>
        </form>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {categories.map(row => <li key={row.package}>{row.package} · {row.category}</li>)}
        </ul>
      </section>

      <section className="col" style={{ gap: 8 }}>
        <div className="kicker">days</div>
        <table>
          <thead>
            <tr>
              {['day', 'kind', 'home', 'office', 'commute', 'steps', 'screen', 'sleep', 'coverage'].map(heading => (
                <th key={heading} style={{ textAlign: 'left', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)' }}>{heading}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {days.map(day => (
              <tr key={day.day}>
                <td>{day.day}</td>
                <td>{day.dayKind}</td>
                <td>{day.homeMinutes}</td>
                <td>{day.officeMinutes}</td>
                <td>{day.commuteMinutes}</td>
                <td>{day.steps ?? '—'}</td>
                <td>{day.screenMinutes}</td>
                <td>{day.sleepMinutes ?? '—'}</td>
                <td>{Math.round(day.locationCoverage * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!days.length && <div style={{ color: 'var(--ink-3)', fontSize: 13 }}>No confirmed days yet.</div>}
      </section>
      {error && <div role="alert" style={{ color: 'var(--rose)', fontFamily: 'var(--mono)', fontSize: 12 }}>{error}</div>}
    </div>
  );
}

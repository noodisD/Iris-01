import { api, upload } from './client';

export interface Place {
  id: number;
  name: string;
  kind: 'home' | 'office' | 'other';
  lat: number;
  lon: number;
  radiusM: number;
  source: 'owner' | 'timeline';
}

export interface DayFeature {
  day: string;
  dayKind: string;
  homeMinutes: number;
  officeMinutes: number;
  commuteMinutes: number;
  commuteMode: string | null;
  steps: number | null;
  stepsFullDay: boolean;
  screenMinutes: number;
  screenByCategory: Record<string, number>;
  sleepMinutes: number | null;
  locationCoverage: number;
}

export interface PlaceSuggestions {
  home: { lat: number; lon: number } | null;
  office: { lat: number; lon: number } | null;
}

export function listPlaces(): Promise<{ places: Place[] }> {
  return api.get('/places');
}

export function suggestPlaces(): Promise<PlaceSuggestions> {
  return api.get('/places/suggestions');
}

export function createPlace(body: Omit<Place, 'id' | 'source'> & { source?: Place['source'] }): Promise<Place> {
  return api.post('/places', body);
}
export function updatePlace(place: Place): Promise<Place> {
  return api.patch(`/places/${place.id}`, { name: place.name, kind: place.kind, lat: place.lat, lon: place.lon, radiusM: place.radiusM });
}

export function deletePlace(id: number): Promise<{ status: string }> {
  return api.del(`/places/${id}`);
}

export function confirmTimelineRange(start: string, end: string): Promise<{ confirmed: number[] }> {
  return api.post('/sensors/confirm-range', { start, end, links: {} });
}


export function listDays(): Promise<{ days: DayFeature[] }> {
  return api.get('/days');
}
export function listCategories(): Promise<{ categories: { package: string; category: string }[] }> {
  return api.get('/app-categories');
}

export function saveCategory(packageName: string, category: string): Promise<{ package: string; category: string }> {
  return api.put('/app-categories', { package: packageName, category });
}

export function uploadTimeline(file: File): Promise<{ batches: number[]; observations: number; dropped: number }> {
  const body = new FormData();
  body.append('file', file);
  return upload('/sensors/import/google-timeline', body);
}

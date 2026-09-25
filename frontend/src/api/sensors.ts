import { api } from './client';

export interface SensorObservation {
  source_type: string;
  occurred_at: string | null;
  value_num: number | null;
  value_text: string | null;
  lat: number | null;
  lon: number | null;
  payload_hash: string;
  origin_package?: string;
}

export interface SensorBatch {
  id: number;
  source: string;
  received_at: string;
  review_day: string | null;
  last_delivery_at: string | null;
  status: 'pending' | 'confirmed' | 'rejected' | 'errored';
  observation_count: number;
  dropped_count: number;
  clock_skew_seconds: number | null;
  parsed_payload?: {
    device?: string;
    exported_at?: string;
    observations: SensorObservation[];
  } | null;
  theme_links: Record<string, number | null>;
}


export async function listBatches(): Promise<SensorBatch[]> {
  return api.get('/sensors/batches');
}

export async function getBatch(id: number | string): Promise<SensorBatch> {
  return api.get(`/sensors/batches/${id}`);
}

export async function confirmBatch(id: number | string, links: Record<string, number | null>, observationCount: number): Promise<SensorBatch> {
  return api.post(`/sensors/batches/${id}/confirm`, { links, observation_count: observationCount });
}

export async function rejectBatch(id: number | string): Promise<SensorBatch> {
  return api.post(`/sensors/batches/${id}/reject`);
}

export async function deleteBatch(id: number | string): Promise<void> {
  return api.del(`/sensors/batches/${id}`);
}

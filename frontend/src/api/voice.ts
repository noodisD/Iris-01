/**
 * Talking with IRIS (ADR-0025): speech in and out around an ordinary chat turn.
 *   GET  /api/voice/estimate    → what one spoken turn costs; sends nothing
 *   POST /api/voice/transcribe  → what the owner said, as text; audio not kept
 *   POST /api/voice/speech      → IRIS's words as MP3
 */
import { api, postRaw } from './client';

export interface VoiceEstimate {
  model: string;
  transcriptionModel: string;
  speechModel: string;
  tokensIn: number;
  perTurn: string;
}

export function getVoiceEstimate(): Promise<VoiceEstimate> {
  return api.get('/voice/estimate');
}

export async function transcribe(audio: Blob, signal?: AbortSignal): Promise<string> {
  const form = new FormData();
  form.append('audio', audio, 'turn.wav');
  const res = await postRaw('/voice/transcribe', { body: form, signal }, 'IRIS could not hear that.');
  return ((await res.json()) as { text: string }).text;
}

export async function speech(text: string, signal?: AbortSignal): Promise<ArrayBuffer> {
  const res = await postRaw('/voice/speech', {
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }), signal,
  }, 'IRIS could not speak that.');
  return res.arrayBuffer();
}

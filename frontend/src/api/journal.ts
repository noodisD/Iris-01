/**
 * Journal API — WIRED LIVE (single-user backend; mapped onto reflections).
 *   GET  /api/journal              → JournalListResponse   (newest first)
 *   POST /api/journal              → JournalEntry          (create)
 */

import { api } from './client';
import type { JournalEntry, JournalListResponse, JournalWrite } from '@/types/api';

export async function listJournal(cursor?: string): Promise<JournalListResponse> {
  return api.get(`/journal${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`);
}

export async function createEntry(input: JournalWrite): Promise<JournalEntry> {
  return api.post('/journal', input);
}

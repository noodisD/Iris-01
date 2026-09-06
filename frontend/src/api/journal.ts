/**
 * Journal API — WIRED LIVE (single-user backend; mapped onto reflections).
 *   GET  /api/journal              → JournalListResponse   (newest first)
 *   POST /api/journal              → JournalEntry          (create)
 */

import { api } from './client';
import type { JournalEntry, JournalListResponse } from '@/types/api';

export async function listJournal(cursor?: string): Promise<JournalListResponse> {
  return api.get(`/journal${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`);
}

export async function createEntry(input: Pick<JournalEntry, 'lines' | 'mood'>): Promise<JournalEntry> {
  return api.post('/journal', input);
}

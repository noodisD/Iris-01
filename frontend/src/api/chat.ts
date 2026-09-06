/**
 * Chat / conversation API — WIRED LIVE (single-user backend).
 *
 * Backend endpoints (iris_api.py):
 *   GET    /api/conversations/current               → Conversation
 *   GET    /api/conversations/:id/messages          → ChatMessage[]
 *   GET    /api/conversations/:id/inferred          → InferredItem[]  (stub: [])
 *   POST   /api/conversations/:id/messages/stream   → SSE of token events (IRIS's reply)
 *
 * Note: there is no POST /messages. The user message is persisted server-side
 * inside the stream endpoint's companion.chat(), so sendMessage() is
 * client-synthesized (no backend write) to avoid double-persisting it.
 */

import { api, sse } from './client';
import type { ChatMessage, Conversation, InferredItem } from '@/types/api';

export async function getCurrentConversation(): Promise<Conversation> {
  return api.get<Conversation>('/conversations/current');
}

export async function getMessages(conversationId: string): Promise<ChatMessage[]> {
  return api.get<ChatMessage[]>(`/conversations/${conversationId}/messages`);
}

export async function sendMessage(conversationId: string, text: string): Promise<ChatMessage> {
  // Client-synthesized user message. Persistence happens server-side in the
  // stream endpoint (companion.chat persists both the user line and the reply).
  return {
    id: `m_${Date.now()}`,
    conversationId,
    role: 'user',
    text,
    createdAt: new Date().toISOString(),
  };
}

/**
 * Stream IRIS's reply. The backend runs companion.chat() and emits the reply as
 * `data: {"text": "..."}` chunks followed by `data: {"done": true, "messageId": "..."}`.
 * (`tone` is accepted for signature compatibility; the backend doesn't use it yet.)
 */
export async function* streamReply(
  conversationId: string,
  userText: string,
  _tone: 'clinical' | 'warm' | 'playful' = 'warm',
): AsyncGenerator<{ text: string; done?: boolean; messageId?: string }> {
  yield* sse<{ text: string; done?: boolean; messageId?: string }>(
    `/conversations/${conversationId}/messages/stream`,
    { text: userText },
  );
}

export async function getInferred(conversationId: string): Promise<InferredItem[]> {
  return api.get<InferredItem[]>(`/conversations/${conversationId}/inferred`);
}

/**
 * Chat / conversation API (single-user backend).
 *
 *   POST /api/conversations                      → Conversation (empty open)
 *   GET  /api/conversations/current              → Conversation (latest open only)
 *   GET  /api/conversations/:id/messages         → ChatMessage[] for that open
 *
 * There is no POST /messages: the stream endpoint stores the owner's message
 * itself, so the bubble shown before the reply arrives is client-side only.
 */

import { api, sse } from './client';
import type { ChatMessage, Conversation } from '@/types/api';

/** A new empty open. Earlier messages stay stored and are not returned here. */
export async function startConversation(): Promise<Conversation> {
  return api.post<Conversation>('/conversations', {});
}

export async function getCurrentConversation(): Promise<Conversation> {
  return api.get<Conversation>('/conversations/current');
}

export async function getMessages(conversationId: string): Promise<ChatMessage[]> {
  return api.get<ChatMessage[]>(`/conversations/${conversationId}/messages`);
}

/** The owner's message as shown while the reply is written; stored by the stream. */
export function draftUserMessage(conversationId: string, text: string): ChatMessage {
  return {
    id: `m_${Date.now()}`,
    conversationId,
    role: 'user',
    text,
    createdAt: new Date().toISOString(),
  };
}

/** A reply that failed. `saved` says the owner's message reached the server and
 *  was stored before the failure, so it will be in the history. */
export class ReplyFailed extends Error {
  saved: boolean;
  constructor(message: string, saved: boolean) {
    super(message);
    this.saved = saved;
  }
}

type StreamEvent = { text?: string; done?: boolean; messageId?: string; error?: string; saved?: boolean };

/**
 * IRIS's reply, fragment by fragment, as the model writes it. A failure the
 * server reports is thrown as ReplyFailed rather than yielded as text — it used
 * to arrive as a reply reading "I encountered an error…", in IRIS's voice.
 */
export async function* streamReply(
  conversationId: string,
  userText: string,
): AsyncGenerator<{ text: string; done?: boolean; messageId?: string }> {
  for await (const ev of sse<StreamEvent>(`/conversations/${conversationId}/messages/stream`, { text: userText })) {
    // Default false: the draft is kept unless the server says the message was
    // stored. Defaulting the other way threw away what they wrote on the word
    // of a server that had not said it.
    if (ev.error !== undefined) throw new ReplyFailed(ev.error, ev.saved ?? false);
    yield { text: ev.text ?? '', done: ev.done, messageId: ev.messageId };
  }
}

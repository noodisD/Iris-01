import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import * as chatApi from '@/api/chat';
import type { ChatMessage } from '@/types/api';

export function useConversation() {
  return useQuery({ queryKey: qk.conversation, queryFn: chatApi.getCurrentConversation });
}

export function useMessages(conversationId: string | undefined) {
  return useQuery({
    queryKey: conversationId ? qk.messages(conversationId) : ['noop'],
    queryFn:  () => chatApi.getMessages(conversationId!),
    enabled:  !!conversationId,
  });
}

/**
 * Send a message and stream IRIS's reply into the cache as it is written.
 *
 * A failure used to leave both optimistic bubbles on screen — the owner's
 * message and an empty reply marked as still streaming, forever — with no
 * error shown. Now the placeholder goes, the screen is reconciled with what the
 * server actually stored, and the error is returned for the screen to show.
 */
export function useSendMessage(conversationId: string | undefined) {
  const qc = useQueryClient();
  const key = conversationId ? qk.messages(conversationId) : ['noop'];

  return useMutation({
    mutationFn: async (text: string) => {
      if (!conversationId) throw new Error('No active conversation');

      const userMsg = chatApi.draftUserMessage(conversationId, text);
      const replyId = `m_stream_${Date.now()}`;
      qc.setQueryData<ChatMessage[]>(key, (old) => [
        ...(old ?? []),
        userMsg,
        { id: replyId, conversationId, role: 'iris', text: '', createdAt: new Date().toISOString(), streaming: true },
      ]);

      try {
        let buffer = '';
        let finalId: string | undefined;
        let finished = false;
        for await (const ev of chatApi.streamReply(conversationId, text)) {
          if (ev.done) { finalId = ev.messageId; finished = true; break; }
          buffer += ev.text;
          qc.setQueryData<ChatMessage[]>(key, (old) =>
            (old ?? []).map(m => m.id === replyId ? { ...m, text: buffer } : m),
          );
        }
        // A stream that stops without its `done` event is an interrupted
        // reply, not a finished one: the connection dropped, and IRIS saved
        // nothing in its own name. Saying "complete" left a half sentence on
        // screen as though it were the whole answer.
        if (!finished) throw new chatApi.ReplyFailed('The reply was interrupted.', true);
        qc.setQueryData<ChatMessage[]>(key, (old) =>
          (old ?? []).map(m => m.id === replyId ? { ...m, id: finalId ?? replyId, streaming: false } : m),
        );
      } catch (err) {
        // Remove what this turn added, then take the server's word for what
        // was stored: the owner's message comes back if it was saved.
        qc.setQueryData<ChatMessage[]>(key, (old) =>
          (old ?? []).filter(m => m.id !== replyId && m.id !== userMsg.id),
        );
        await qc.invalidateQueries({ queryKey: key });
        throw err;
      }
      return userMsg;
    },
  });
}

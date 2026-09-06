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

export function useInferred(conversationId: string | undefined) {
  return useQuery({
    queryKey: conversationId ? qk.inferred(conversationId) : ['noop'],
    queryFn:  () => chatApi.getInferred(conversationId!),
    enabled:  !!conversationId,
  });
}

/**
 * Send a user message + stream Iris's reply. Updates the React Query cache
 * optimistically so the chat scrolls without a refetch.
 */
export function useSendMessage(conversationId: string | undefined, tone: 'clinical' | 'warm' | 'playful') {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: async (text: string) => {
      if (!conversationId) throw new Error('No active conversation');

      // 1) Append user message immediately
      const userMsg = await chatApi.sendMessage(conversationId, text);
      qc.setQueryData<ChatMessage[]>(qk.messages(conversationId), (old) => [...(old ?? []), userMsg]);

      // 2) Open a streaming reply placeholder
      const replyId = `m_stream_${Date.now()}`;
      qc.setQueryData<ChatMessage[]>(qk.messages(conversationId), (old) => [
        ...(old ?? []),
        { id: replyId, conversationId, role: 'iris', text: '', createdAt: new Date().toISOString(), streaming: true },
      ]);

      // 3) Stream tokens
      let buffer = '';
      let finalId: string | undefined;
      for await (const ev of chatApi.streamReply(conversationId, text, tone)) {
        if (ev.done) { finalId = ev.messageId; break; }
        buffer += ev.text;
        qc.setQueryData<ChatMessage[]>(qk.messages(conversationId), (old) =>
          (old ?? []).map(m => m.id === replyId ? { ...m, text: buffer } : m),
        );
      }

      // 4) Finalize
      qc.setQueryData<ChatMessage[]>(qk.messages(conversationId), (old) =>
        (old ?? []).map(m => m.id === replyId ? { ...m, id: finalId ?? replyId, streaming: false } : m),
      );

      // Refresh inferred items in the rail
      qc.invalidateQueries({ queryKey: qk.inferred(conversationId) });

      return userMsg;
    },
  });
}

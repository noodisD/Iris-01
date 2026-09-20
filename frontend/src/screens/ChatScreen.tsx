import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { useConversation, useMessages, useSendMessage } from '@/hooks/useChat';
import { useUser } from '@/hooks/useData';
import { ReplyFailed } from '@/api/chat';
import { LoadingState, ErrorState } from '@/components/states';
import type { ChatMessage } from '@/types/api';

/** The part of the day it actually is. The header said "evening check-in" at
 *  every hour. */
function partOfDay(d = new Date()): string {
  const h = d.getHours();
  return h < 12 ? 'morning' : h < 18 ? 'afternoon' : 'evening';
}

/** Written today, by the owner. The footer counted every user message loaded. */
function sentToday(messages: ChatMessage[]): number {
  const today = new Date().toDateString();
  return messages.filter(m => m.role === 'user' && new Date(m.createdAt).toDateString() === today).length;
}

function Bubble({ msg }: { msg: ChatMessage }) {
  if (msg.role === 'iris' || msg.role === 'system') {
    return (
      <div className="row" style={{ gap: 14, alignItems: 'flex-start', maxWidth: 640, marginBottom: 22, animation: 'fadeUp 0.4s ease' }}>
        <div className="iris-orb sm" style={{ marginTop: 6 }} />
        <div className="col" style={{ gap: 8 }}>
          <div className="serif" style={{ fontStyle: 'italic', fontSize: 21, lineHeight: 1.35, color: 'var(--ink)' }}>
            {msg.text}
            {msg.streaming && <span style={{ opacity: 0.5 }}>▌</span>}
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="row" style={{ justifyContent: 'flex-end', marginBottom: 22, animation: 'fadeUp 0.4s ease' }}>
      <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-soft)', color: 'var(--ink-2)', padding: '10px 14px', borderRadius: 12, maxWidth: 460, fontSize: 14, lineHeight: 1.55 }}>{msg.text}</div>
    </div>
  );
}

export function ChatScreen() {
  const { data: user } = useUser();
  const { data: convo, isLoading, isError, refetch } = useConversation();
  const { data: messages } = useMessages(convo?.id);
  const send = useSendMessage(convo?.id);
  const [params, setParams] = useSearchParams();

  // "Ask Iris about this" on an insight arrives as ?draft=… — offered in the
  // box for the owner to edit or send, never sent on their behalf.
  const [draft, setDraft] = React.useState(() => params.get('draft') ?? '');
  React.useEffect(() => {
    if (params.has('draft')) setParams({}, { replace: true });
  }, [params, setParams]);
  const [failure, setFailure] = React.useState<string | null>(null);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const el = scrollRef.current;
    if (el) requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
  }, [messages, send.isPending]);

  const submit = (text = draft) => {
    const t = text.trim();
    if (!t) return;
    setDraft('');
    setFailure(null);
    send.mutate(t, {
      onError: (err) => {
        // If the server never stored the message, give it back to the owner;
        // if it did, it is already in the history and re-sending would repeat it.
        if (!(err instanceof ReplyFailed && err.saved)) setDraft(cur => cur || t);
        setFailure(err instanceof ReplyFailed && err.saved
          ? `Your message was saved, but Iris couldn't reply: ${err.message}`
          : `Couldn't reach Iris: ${err instanceof Error ? err.message : String(err)}`);
      },
    });
  };

  if (isLoading) return <LoadingState />;
  if (isError || !convo) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      <div className="col" style={{ flex: 1, minWidth: 0 }}>
        <div className="row" style={{ alignItems: 'center', justifyContent: 'space-between', padding: '20px 40px 14px', borderBottom: '1px solid var(--line-soft)' }}>
          <div className="row" style={{ gap: 12, alignItems: 'center' }}>
            <span className="dot sage" style={{ animation: 'breathe 3s ease-in-out infinite' }} />
            <span className="kicker">Iris · listening</span>
          </div>
          <div className="row" style={{ gap: 8 }}>
            {user && <span className="tag">day {user.dayInJourney}</span>}
            <span className="tag"><span className="dot sage" /> private</span>
          </div>
        </div>

        <div ref={scrollRef} style={{ flex: 1, overflow: 'auto', padding: '40px 60px 24px' }}>
          <div className="col" style={{ maxWidth: 720, margin: '0 auto' }}>
            <div className="kicker" style={{ marginBottom: 14 }}>— {partOfDay()} check-in</div>
            <div className="serif" style={{ fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em', marginBottom: 38 }}>
              How was today,<br /><span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>really?</span>
            </div>
            {(messages ?? []).map(m => <Bubble key={m.id} msg={m} />)}
            {send.isPending && !messages?.some(m => m.streaming) && (
              <div className="row" style={{ gap: 14, alignItems: 'flex-start', marginBottom: 22 }}>
                <div className="iris-orb sm" style={{ marginTop: 6 }} />
                <div className="row" style={{ gap: 4, alignItems: 'center', height: 30 }}>
                  {[0, 0.2, 0.4].map(d => <span key={d} style={{ width: 4, height: 4, borderRadius: 999, background: 'var(--sage)', animation: `blink 1.2s ease-in-out ${d}s infinite` }} />)}
                </div>
              </div>
            )}
          </div>
        </div>

        <div style={{ padding: '14px 60px 28px', borderTop: '1px solid var(--line-soft)', background: 'var(--bg-0)' }}>
          <div style={{ maxWidth: 720, margin: '0 auto' }}>
            {failure && (
              <div role="alert" style={{ marginBottom: 12, fontSize: 12, color: 'var(--rose)', fontFamily: 'var(--mono)', letterSpacing: '0.02em' }}>
                {failure}
              </div>
            )}
            <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 10, padding: '14px 16px', display: 'flex', alignItems: 'flex-end', gap: 12 }}>
              <textarea value={draft} onChange={e => setDraft(e.target.value)}
                // Enter is ignored while a reply is in flight, as the Send
                // button already is: a second turn started mid-stream races the
                // first for the same conversation.
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!send.isPending) submit(); } }}
                placeholder="Talk to Iris… (⏎ to send, ⇧⏎ for new line)" rows={1}
                style={{ flex: 1, background: 'transparent', border: 'none', resize: 'none', color: 'var(--ink)', fontFamily: 'var(--sans)', fontSize: 14, lineHeight: 1.5, outline: 'none', minHeight: 22 }} />
              <button className="btn primary" style={{ padding: '7px 14px' }} onClick={() => submit()} disabled={send.isPending}>Send</button>
            </div>
            <div className="row" style={{ justifyContent: 'space-between', marginTop: 10, fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--ink-4)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
              <span>Stored on this machine · replies generated by OpenAI</span>
              <span>{sentToday(messages ?? [])} messages today</span>
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}

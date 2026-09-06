import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useConversation, useMessages, useInferred, useSendMessage } from '@/hooks/useChat';
import { useUser } from '@/hooks/useData';
import { LoadingState, ErrorState } from '@/components/states';
import type { ChatMessage } from '@/types/api';

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
          {msg.noticed && msg.noticed.length > 0 && (
            <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
              <span className="kicker" style={{ color: 'var(--ink-4)' }}>Noticed</span>
              {msg.noticed.map((n) => (
                <span key={n.key} style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--sage)', borderBottom: '1px dotted var(--sage-dim)', paddingBottom: 1 }}>{n.label}</span>
              ))}
            </div>
          )}
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
  const { data: inferred } = useInferred(convo?.id);
  const tone = user?.preferences.tone ?? 'warm';
  const send = useSendMessage(convo?.id, tone);

  const [draft, setDraft] = React.useState('');
  const scrollRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const el = scrollRef.current;
    if (el) requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
  }, [messages, send.isPending]);

  const submit = () => {
    const t = draft.trim();
    if (!t) return;
    setDraft('');
    send.mutate(t);
  };

  if (isLoading) return <LoadingState />;
  if (isError || !convo) return <ErrorState onRetry={() => refetch()} />;

  const lastIris = [...(messages ?? [])].reverse().find(m => m.role === 'iris');
  const quick = lastIris?.quickReplies ?? [];

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      <div className="col" style={{ flex: 1, minWidth: 0 }}>
        <div className="row" style={{ alignItems: 'center', justifyContent: 'space-between', padding: '20px 40px 14px', borderBottom: '1px solid var(--line-soft)' }}>
          <div className="row" style={{ gap: 12, alignItems: 'center' }}>
            <span className="dot sage" style={{ animation: 'breathe 3s ease-in-out infinite' }} />
            <span className="kicker">Iris · listening</span>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <span className="tag">day {user?.dayInJourney ?? 47}</span>
            <span className="tag"><span className="dot sage" /> private</span>
          </div>
        </div>

        <div ref={scrollRef} style={{ flex: 1, overflow: 'auto', padding: '40px 60px 24px' }}>
          <div className="col" style={{ maxWidth: 720, margin: '0 auto' }}>
            <div className="kicker" style={{ marginBottom: 14 }}>— evening check-in</div>
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
            {quick.length > 0 && (
              <div className="row" style={{ gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
                {quick.map(q => (
                  <button key={q.id} className="btn" onClick={() => send.mutate(q.label)} style={{ borderColor: 'var(--sage-dim)', color: 'var(--sage)' }}>{q.label}</button>
                ))}
              </div>
            )}
            <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 10, padding: '14px 16px', display: 'flex', alignItems: 'flex-end', gap: 12 }}>
              <textarea value={draft} onChange={e => setDraft(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
                placeholder="Talk to Iris… (⏎ to send, ⇧⏎ for new line)" rows={1}
                style={{ flex: 1, background: 'transparent', border: 'none', resize: 'none', color: 'var(--ink)', fontFamily: 'var(--sans)', fontSize: 14, lineHeight: 1.5, outline: 'none', minHeight: 22 }} />
              <button className="btn primary" style={{ padding: '7px 14px' }} onClick={submit} disabled={send.isPending}>Send</button>
            </div>
            <div className="row" style={{ justifyContent: 'space-between', marginTop: 10, fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--ink-4)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
              <span>End-to-end private · processed on device</span>
              <span>{(messages ?? []).filter(m => m.role === 'user').length} messages today</span>
            </div>
          </div>
        </div>
      </div>

      {/* Inferred rail */}
      <aside style={{ width: 280, flexShrink: 0, borderLeft: '1px dashed var(--line)', padding: '36px 24px 24px', overflow: 'auto' }}>
        <div className="kicker">From this conversation</div>
        <h3 className="serif" style={{ margin: '8px 0 18px', fontSize: 22, lineHeight: 1, color: 'var(--ink)' }}>
          Iris is hearing<span style={{ color: 'var(--sage)' }}>.</span>
        </h3>
        <div className="col" style={{ gap: 14 }}>
          {(inferred ?? []).map((it, i) => (
            <div key={i} className="col" style={{ gap: 4 }}>
              <div className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between' }}>
                <span className="kicker" style={{ color: 'var(--ink-3)' }}>{it.tag}</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink-4)' }}>{Math.round(it.confidence * 100)}%</span>
              </div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink)' }}>{it.value}</div>
              <div style={{ height: 1, background: 'var(--line-soft)', position: 'relative', marginTop: 2 }}>
                <div style={{ position: 'absolute', left: 0, top: 0, height: 1, width: `${it.confidence * 100}%`, background: 'var(--sage)' }} />
              </div>
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}

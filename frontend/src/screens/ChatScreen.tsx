import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMessages, useNewConversation, useSendMessage } from '@/hooks/useChat';
import { useUser } from '@/hooks/useData';
import { ReplyFailed } from '@/api/chat';
import { LoadingState, ErrorState } from '@/components/states';
import type { ChatMessage } from '@/types/api';
import { Mic } from 'lucide-react';
import { TalkIntro, TalkMode } from '@/components/TalkMode';
import { useTalk } from '@/hooks/useTalk';
import { Button, Lens } from '@/ui';
import styles from './ChatScreen.module.css';

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
      <div className={styles.iris}>
        <Lens size={20} />
        <p className={styles.irisText}>
          {msg.text}
          {msg.streaming && <span className={styles.caret} aria-hidden>▌</span>}
        </p>
      </div>
    );
  }
  return (
    <div className={styles.mine}><p className={styles.mineText}>{msg.text}</p></div>
  );
}

export function ChatScreen() {
  const { data: user } = useUser();
  const [visit] = React.useState(() => crypto.randomUUID());
  const { data: convo, isLoading, isError, refetch } = useNewConversation(visit);
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

  // Talking (ADR-0025): the same turn as typing, heard and spoken. "asking"
  // shows what it sends and costs; nothing is sent before Start talking.
  const [talkStage, setTalkStage] = React.useState<'off' | 'asking' | 'on'>('off');
  const talk = useTalk((text, onFragment) => send.mutateAsync({ text, voice: true, onFragment }));
  const talkControls = React.useMemo(() => ({
    ...talk, end: () => { talk.end(); setTalkStage('off'); },
  }), [talk]);

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

  const partTitle = partOfDay();
  return (
    <div className={styles.chat}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>Chat</h1>
          <p className={styles.sub}>{partTitle[0].toUpperCase() + partTitle.slice(1)} check-in{user ? `, day ${user.dayInJourney}` : ''}</p>
        </div>
        <p className={styles.privacy}>Stored on this laptop. Replies come from OpenAI.</p>
      </header>

      <div ref={scrollRef} className={styles.scroll}>
        <div className={styles.thread} aria-live="polite">
          <div className={styles.iris}>
            <Lens size={20} />
            <p className={styles.irisText}>How was today, really?</p>
          </div>
          {(messages ?? []).map(m => <Bubble key={m.id} msg={m} />)}
          {send.isPending && !messages?.some(m => m.streaming) && (
            <div className={styles.iris} aria-label="Iris is replying">
              <Lens size={20} />
              <span className={styles.typing}><i /><i /><i /></span>
            </div>
          )}
        </div>
      </div>

      <div className={styles.composerWrap}>
        <div className={styles.composerInner}>
          {talkStage === 'asking' && (
            <TalkIntro onCancel={() => setTalkStage('off')}
              onStart={() => { setTalkStage('on'); void talk.start(); }} />
          )}
          {talkStage === 'on' && <TalkMode talk={talkControls} />}
          {talkStage === 'off' && <>
          {failure && <p role="alert" className={styles.failure}>{failure}</p>}
          <div className={styles.composer}>
            <textarea value={draft} onChange={e => setDraft(e.target.value)} aria-label="Message to Iris"
              // Enter is ignored while a reply is in flight, as the Send
              // button already is: a second turn started mid-stream races the
              // first for the same conversation.
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!send.isPending) submit(); } }}
              placeholder="Talk to Iris. Enter sends, Shift+Enter adds a line." rows={1} className={styles.input} />
            <Button variant="quiet" icon={<Mic aria-hidden />} onClick={() => setTalkStage('asking')}
              disabled={send.isPending}>Talk</Button>
            <Button variant="primary" onClick={() => submit()} disabled={send.isPending}>Send</Button>
          </div>
          <p className={styles.meta}>{sentToday(messages ?? [])} messages today</p>
          </>}
        </div>
      </div>
    </div>
  );
}

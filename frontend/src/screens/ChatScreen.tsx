import React from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useEvidencePreview, useMessages, useNewConversation, useSendMessage } from '@/hooks/useChat';
import { useUser } from '@/hooks/useData';
import { ReplyFailed } from '@/api/chat';
import { parseEvidenceRef } from '@/lib/evidence';
import { LoadingState, ErrorState } from '@/components/states';
import type { ChatMessage, DayDifferenceDetail, EvidenceRef, InsightDetail,
  PatternDetail, PersonalAccount } from '@/types/api';
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

function EvidenceAccount({ account }: { account: PersonalAccount }) {
  return <article className={styles.sourceAccount}>
    <p>Recorded {account.recordedOn ?? 'date unknown'} · {account.recordKind.replace('_', ' ')}</p>
    <p>{account.situation} {account.response} {account.selfReport}</p>
    {account.explanation && <p>You wrote: {account.explanation}</p>}
    {account.citations.map((citation, index) =>
      <blockquote key={index}>{citation.text}{' '}
        {citation.sourceType === 'reflection' && <Link
          to={`/journal?entry=${encodeURIComponent(String(citation.entryId))}`}>Open entry</Link>}
      </blockquote>)}
  </article>;
}

/** A corrected account stays in detail under Your corrections, not ordinary chat evidence. */
function previewGroups(detail: PatternDetail | InsightDetail) {
  return Object.entries(detail.groups).flatMap(([dynamicId, groups]) => {
    const included = new Map<string, Set<string>>();
    for (const row of detail.memberships[dynamicId] ?? []) {
      if (row.excluded || row.ownerVerdict === 'no' || row.groupId === null) continue;
      if (!included.has(row.groupId)) included.set(row.groupId, new Set());
      included.get(row.groupId)!.add(row.accountId);
    }
    return groups.map(group => ({
      ...group, dynamicId,
      accountIds: group.accountIds.filter(id => included.get(group.id)?.has(id) && detail.accounts[id]),
    })).filter(group => group.accountIds.length > 0);
  });
}

function EvidencePreview({ reference, evidence }: {
  reference: EvidenceRef; evidence: PatternDetail | InsightDetail | DayDifferenceDetail;
}) {
  if (reference.kind === 'dynamic') {
    const detail = evidence as PatternDetail;
    const p = detail.pattern;
    const groups = previewGroups(detail);
    const contrary = groups.find(group => group.role === 'exception');
    const selected = [...(contrary ? [contrary] : []), ...groups.filter(group => group !== contrary)].slice(0, 4);
    return <div>
      <p>{p.context.text} → {p.response.text}</p>
      {p.ownerMeanings.map((meaning, index) => <p key={index}>You wrote: {meaning.text}</p>)}
      <p>One possible explanation (not established): {p.possibleMeaning?.text ?? 'Not recorded'}</p>
      <p>Another possibility: {p.alternative?.text ?? 'Not recorded'}</p>
      <p>{groups.length} checked groups; {p.unknownAccountCount} unclear accounts.
        Previewing {selected.length} groups; see detail for the complete record.</p>
      {selected.map(group => <section key={`${group.dynamicId}/${group.id}`}><h3>{group.role.replace('_', ' ')}</h3>
        {group.accountIds.map(id =>
          <EvidenceAccount key={id} account={detail.accounts[id]} />)}</section>)}
    </div>;
  }
  if (reference.kind === 'personal_insight') {
    const detail = evidence as InsightDetail;
    const insight = detail.insight;
    const groups = previewGroups(detail);
    const contrary = groups.find(group => insight.contraryGroups.includes(group.id));
    const selected = [...(contrary ? [contrary] : []), ...groups.filter(group => group !== contrary)].slice(0, 4);
    return <div>
      <p>{insight.observation.text}</p>
      <p>One possible explanation (not established): {insight.possibleMeaning.text}</p>
      <p>Another possibility: {insight.alternative.text}</p>
      <p>{groups.length} checked groups; {insight.unknownAccountIds.length} unclear accounts.
        Previewing {selected.length} groups; see detail for the complete record.</p>
      {selected.map(group => <section key={`${group.dynamicId}/${group.id}`}><h3>{group.role.replace('_', ' ')}</h3>
        {group.accountIds.map(id =>
          <EvidenceAccount key={id} account={detail.accounts[id]} />)}</section>)}
    </div>;
  }
  const days = evidence as DayDifferenceDetail;
  return <div>
    <p>{days.difference.leftLabel}: {days.difference.leftMean} across {days.difference.leftCount} days;
      {days.difference.rightLabel}: {days.difference.rightMean} across {days.difference.rightCount} days.</p>
    {[...days.leftDays.slice(0, 5), ...days.rightDays.slice(0, 5)].map(day =>
      <p key={day.day}>{day.day} · score {day.value} · {day.splitValue}{' '}
        {day.entryIds.map(id => <Link key={id} to={`/journal?entry=${id}`}>Check-in</Link>)}</p>)}
  </div>;
}

function discussionDraftKey(ref: EvidenceRef) {
  return `iris:discussion-draft:${JSON.stringify(ref)}`;
}

export function ChatScreen() {
  const { data: user } = useUser();
  const [visit] = React.useState(() => crypto.randomUUID());
  const { data: convo, isLoading, isError, refetch } = useNewConversation(visit);
  const { data: messages } = useMessages(convo?.id);
  const send = useSendMessage(convo?.id);
  const [params, setParams] = useSearchParams();
  const [initialEvidence] = React.useState(() => params.get('evidence'));
  const [reference, setReference] = React.useState<EvidenceRef | null>(
    () => parseEvidenceRef(initialEvidence));
  const [invalidReference, setInvalidReference] = React.useState(
    () => initialEvidence !== null && parseEvidenceRef(initialEvidence) === null);
  const preview = useEvidencePreview(reference);
  const savedDraft = React.useRef(reference ? sessionStorage.getItem(discussionDraftKey(reference)) : null);
  const [draft, setDraft] = React.useState(savedDraft.current ?? '');
  const draftTouched = React.useRef(savedDraft.current !== null);
  const seeded = React.useRef(savedDraft.current !== null);
  React.useEffect(() => {
    if (preview.data && !preview.isFetching && !seeded.current && !draftTouched.current) {
      seeded.current = true;
      setDraft(preview.data.question);
    }
  }, [preview.data, preview.isFetching]);
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
    const draftKey = reference && discussionDraftKey(reference);
    if (!t || invalidReference || (reference &&
      (preview.isFetching || preview.isError || !preview.data || preview.data.changed))) return;
    const submittedDraft = draftKey ? sessionStorage.getItem(draftKey) : null;
    setDraft('');
    setFailure(null);
    draftTouched.current = true;
    send.mutate(reference ? { text: t, evidenceRef: reference } : t, {
      onSuccess: () => {
        if (draftKey && sessionStorage.getItem(draftKey) === submittedDraft) {
          sessionStorage.removeItem(draftKey);
        }
      },
      onError: (err) => {
        // A new draft written during the stream belongs to the next turn.
        const hasNewDraft = Boolean(draftKey && sessionStorage.getItem(draftKey) !== submittedDraft);
        if (!(err instanceof ReplyFailed && err.saved) && !hasNewDraft) {
          setDraft(cur => cur || t);
        }
        if (draftKey && !hasNewDraft) {
          if (err instanceof ReplyFailed && err.saved) sessionStorage.removeItem(draftKey);
          else sessionStorage.setItem(draftKey, t);
        }
        if (reference) void preview.refetch();
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
          {(reference || invalidReference) && <section aria-label="Selected evidence" className={styles.evidence}>
            <div className={styles.evidenceHead}>
              <strong>Selected evidence</strong>
              <Button size="sm" onClick={() => {
                if (reference) sessionStorage.removeItem(discussionDraftKey(reference));
                setReference(null); setInvalidReference(false);
                setParams({}, { replace: true });
              }}>Remove</Button>
            </div>
            {invalidReference ? <p role="alert">That evidence link is invalid. Return to Patterns or Insights.</p>
              : preview.isPending || preview.isFetching ? <p>Opening current evidence…</p>
              : preview.isError || !preview.data ? <>
                <p role="alert">Selected evidence is unavailable or no longer qualifies.</p>
                <Button size="sm" onClick={() => void preview.refetch()}>Retry preview</Button>
              </> : <>
                <h2>{preview.data.title}</h2>
                <EvidencePreview reference={reference!} evidence={preview.data.evidence} />
                {preview.data.changed && <div role="alert">
                  <p>Review updated evidence before sending. Your draft has not been sent.</p>
                  <Button size="sm" onClick={() => {
                    if (reference) sessionStorage.removeItem(discussionDraftKey(reference));
                    sessionStorage.setItem(discussionDraftKey(preview.data!.ref), draft);
                    setReference(preview.data!.ref);
                    setParams({ evidence: JSON.stringify(preview.data!.ref) }, { replace: true });
                  }}>Use updated evidence</Button>
                </div>}
              </>}
            {reference && <Link to={reference.kind === 'dynamic'
              ? `/patterns/${encodeURIComponent(reference.dynamicId)}?range=${reference.range}`
              : `/insights?range=${reference.range}`}>Back to source</Link>}
          </section>}
          {talkStage === 'asking' && (
            <TalkIntro onCancel={() => setTalkStage('off')}
              onStart={() => { setTalkStage('on'); void talk.start(); }} />
          )}
          {talkStage === 'on' && <TalkMode talk={talkControls} />}
          {talkStage === 'off' && <>
          {failure && <p role="alert" className={styles.failure}>{failure}</p>}
          <div className={styles.composer}>
            <textarea value={draft} onChange={e => {
              draftTouched.current = true;
              setDraft(e.target.value);
              if (reference) sessionStorage.setItem(discussionDraftKey(reference), e.target.value);
            }}
              aria-label="Message to Iris"
              // Enter is ignored while a reply is in flight, as the Send
              // button already is: a second turn started mid-stream races the
              // first for the same conversation.
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!send.isPending) submit(); } }}
              placeholder="Talk to Iris. Enter sends, Shift+Enter adds a line." rows={1} className={styles.input} />
            <Button variant="quiet" icon={<Mic aria-hidden />} onClick={() => setTalkStage('asking')}
              disabled={send.isPending || Boolean(reference) || invalidReference}>Talk</Button>
            <Button variant="primary" onClick={() => submit()}
              disabled={send.isPending || invalidReference || Boolean(reference &&
                (preview.isFetching || preview.isError || !preview.data || preview.data.changed))}>Send</Button>
          </div>
          {(reference || invalidReference) && <p className={styles.meta}>
            Selected evidence is for typed discussion. Remove it to start Talk.</p>}
          <p className={styles.meta}>{sentToday(messages ?? [])} messages today</p>
          </>}
        </div>
      </div>
    </div>
  );
}

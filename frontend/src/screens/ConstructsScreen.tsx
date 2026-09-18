import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  useConfirmConstruct, useConstructCandidates, useDiscoverConstructs, useRejectConstruct,
} from '@/hooks/useConstructs';
import { LoadingState, ErrorState, EmptyState } from '@/components/states';
import { formatEventDate, DAY_LONG } from '@/lib/dates';
import type { ConstructCandidate } from '@/types/api';

function Candidate({ c }: { c: ConstructCandidate }) {
  const confirm = useConfirmConstruct();
  const reject = useRejectConstruct();
  const nav = useNavigate();
  const busy = confirm.isPending || reject.isPending;

  const span = c.spanStart && c.spanEnd
    ? `${formatEventDate(c.spanStart, DAY_LONG)} – ${formatEventDate(c.spanEnd, DAY_LONG)}`
    : null;

  return (
    <article style={{
      padding: '24px 28px', background: 'var(--bg-2)',
      border: '1px solid var(--line-soft)', borderRadius: 12,
      display: 'flex', flexDirection: 'column', gap: 16,
    }}>
      <div className="col" style={{ gap: 6 }}>
        <div className="kicker">
          {c.claimKind === 'behaviour'
            ? 'iris noticed · claims something happened'
            : 'iris noticed · counts what you wrote about'}
        </div>
        <h3 className="serif" style={{ margin: 0, fontSize: 26, lineHeight: 1.1 }}>{c.claim}</h3>
        {span && (
          <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            {span}
          </span>
        )}
      </div>

      {/* The quotes are the point. Confirming means reading the sentences the
          claim rests on — not taking a model's word for the claim. */}
      <div className="col" style={{ gap: 12 }}>
        <div className="kicker">in your own words</div>
        {c.quotes.map((q, i) => (
          <blockquote key={i} style={{ margin: 0, padding: '0 0 0 16px', borderLeft: '2px solid var(--sage-dim)' }}>
            <div className="serif" style={{ fontSize: 17, fontStyle: 'italic', lineHeight: 1.45, color: 'var(--ink)' }}>
              "{q.text}"
            </div>
            {q.citable && q.entryId ? (
              <button
                onClick={() => nav(`/journal?entry=${q.entryId}`)}
                style={{ marginTop: 5, padding: 0, background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--sage)', letterSpacing: '0.08em', textTransform: 'uppercase' }}
              >
                read the entry ↗
              </button>
            ) : (
              <div style={{ marginTop: 5, fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                from a recording · undated, so it is never counted
              </div>
            )}
          </blockquote>
        ))}
      </div>

      <div className="row" style={{ gap: 8, justifyContent: 'flex-end' }}>
        <button className="btn" disabled={busy} onClick={() => reject.mutate(c.id)}>
          {reject.isPending ? 'Setting aside…' : 'Not me'}
        </button>
        <button className="btn primary" disabled={busy} onClick={() => confirm.mutate(c.id)}>
          {confirm.isPending ? 'Measuring…' : 'Yes — count this in my writing'}
        </button>
      </div>
      <div style={{ fontSize: 11, color: 'var(--ink-4)', textAlign: 'right', marginTop: -8 }}>
        Counts how often this comes up in what you wrote. Not how often you did it.
      </div>
    </article>
  );
}

export function ConstructsScreen() {
  const { data, isPending, isError, refetch } = useConstructCandidates();
  const discover = useDiscoverConstructs();
  const [includeStaged, setIncludeStaged] = React.useState(true);

  if (isPending) return <LoadingState label="Iris is fetching what she noticed…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div className="col" style={{ padding: '32px 56px 48px', gap: 28 }}>
      <header className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid var(--line)', paddingBottom: 18 }}>
        <div className="col" style={{ gap: 6 }}>
          <div className="kicker">patterns · awaiting your word</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
            {data.length} to read,<br />
            <span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>none counted yet.</span>
          </h1>
        </div>
        <div className="col" style={{ gap: 8, alignItems: 'flex-end' }}>
          <label className="row" style={{ gap: 6, alignItems: 'center', fontSize: 11, color: 'var(--ink-3)' }}>
            <input type="checkbox" checked={includeStaged}
                   onChange={(e) => setIncludeStaged(e.target.checked)} />
            include voice recordings
          </label>
          <button className="btn primary" disabled={discover.isPending}
                  onClick={() => discover.mutate(includeStaged)}>
            {discover.isPending ? 'Reading your archive…' : 'Read my archive'}
          </button>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink-4)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            sends your entries to the model
          </span>
        </div>
      </header>

      {discover.isError && (
        <div style={{ padding: '12px 16px', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12, color: 'var(--ink-2)' }}>
          The read did not finish. Nothing was changed.
        </div>
      )}

      {data.length === 0 ? (
        <EmptyState
          title="Nothing waiting."
          body="Reading the archive is something you ask for. When Iris finds something that recurs in your writing, it waits here with the quotes it rests on — and counts for nothing until you say so."
        />
      ) : (
        <div className="col" style={{ gap: 18, maxWidth: 860 }}>
          {data.map((c) => <Candidate key={c.id} c={c} />)}
        </div>
      )}
    </div>
  );
}

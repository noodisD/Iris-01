import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  useConfirmConstruct, useConstructCandidates, useDiscoverConstructs, useLastRun, useRejectConstruct,
} from '@/hooks/useConstructs';
import { LoadingState, ErrorState, EmptyState } from '@/components/states';
import { formatEventDate, DAY_LONG } from '@/lib/dates';
import type { ConstructCandidate, DiscoveryRun } from '@/types/api';

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
      {(confirm.isError || reject.isError) && (
        // Without this the buttons simply became usable again, which reads as
        // a misclick rather than as a decision that did not reach the server.
        <div role="alert" style={{ fontSize: 12, color: 'var(--rose)' }}>
          That didn't save. The pattern is still waiting for your decision.
        </div>
      )}

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

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/**
 * What the last read found and why the rest was let go. The support check
 * fails closed, so a model that answers badly empties this screen; without
 * these counts that looked exactly like an archive with nothing to say.
 */
export function RunSummary({ run }: { run: DiscoveryRun }) {
  const d = run.dropped;
  const unchecked = d.unchecked + d.incomplete;
  const letGo = [
    d.mergedAway && `${d.mergedAway} merged into another`,
    unchecked && `${unchecked} because support could not be checked`,
    d.denied && `${d.denied} because a quote denied the claim`,
    d.tooFewSupporting && `${d.tooFewSupporting} with too few supporting quotes`,
    d.alreadyDecided && `${d.alreadyDecided} you had already decided on`,
    d.notEmbedded && `${d.notEmbedded} that could not be stored`,
  ].filter(Boolean) as string[];

  return (
    <div role="status" style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6 }}>
      <span className="kicker" style={{ marginRight: 8 }}>last read</span>
      {plural(run.rawFindings, 'finding')}, {plural(run.staged, 'proposal')}.
      {run.status !== 'complete' && ` ${run.passesCompleted} of ${run.passesPlanned} passes finished.`}
      {run.dropsRecorded
        ? letGo.length > 0 && ` Let go: ${letGo.join(', ')}.`
        : ' This read was made before IRIS counted what it let go.'}
    </div>
  );
}

export function ConstructsScreen() {
  const { data, isPending, isError, refetch } = useConstructCandidates();
  const discover = useDiscoverConstructs();
  const { data: lastRun } = useLastRun();
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

      {lastRun && <RunSummary run={lastRun} />}

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

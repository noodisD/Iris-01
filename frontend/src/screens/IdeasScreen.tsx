import React from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { IdeaGraph } from '@/components/IdeaGraph';
import { IdeaNeighborhood } from '@/components/IdeaNeighborhood';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { HttpError } from '@/api/client';
import {
  useConfirmIdea, useConfirmIdeaLink, useCritiqueIdea, useDiscoverIdeaLinks, useDiscoverIdeas,
  useIdea, useIdeaReview, useIdeasFramework, useRejectIdea, useRejectIdeaCitations,
  useRejectIdeaLink, useUpdateIdea,
} from '@/hooks/useIdeas';
import { formatEventDate, DAY_LONG } from '@/lib/dates';
import type {
  IdeaCitation, IdeaCritique, IdeaDomain, IdeaLink, IdeaPosition, IdeaRun, IdeaSummary,
  IdeasFramework, IdeasReview,
} from '@/types/api';

const POSITIONS: { value: IdeaPosition; label: string }[] = [
  { value: 'exploring', label: 'Exploring' },
  { value: 'endorsed', label: 'I hold this' },
  { value: 'opposed', label: 'I reject this' },
];
const DOMAINS: { value: IdeaDomain; label: string }[] = [
  { value: 'philosophy', label: 'Philosophy' },
  { value: 'economics', label: 'Economics' },
  { value: 'markets', label: 'Markets' },
  { value: 'politics', label: 'Politics' },
  { value: 'ethics', label: 'Ethics' },
  { value: 'learning', label: 'Learning' },
  { value: 'other', label: 'Other' },
];
const STANCE_LABEL: Record<IdeaCitation['stance'], string> = {
  endorsed: 'You endorsed this then',
  questioned: 'You questioned this then',
  opposed: 'You opposed this then',
};
const LINK_LABEL: Record<IdeaLink['kind'], string> = {
  supports: 'supports',
  contradicts: 'contradicts',
  refines: 'refines',
  depends_on: 'depends on',
};
const DROP_LABEL: [keyof IdeaRun['dropped'], string][] = [
  ['invalid_quote', 'a quote was not in the entry'],
  ['not_stated', 'a quote did not show your position'],
  ['unchecked', 'a check could not be completed'],
  ['malformed', 'a reply could not be read'],
  ['already_decided', 'you had already decided'],
  ['duplicate', 'already on record'],
  ['source_changed', 'the entry changed during the read'],
];
const REMOVE_IDEA = 'Remove this idea from your framework? It will not be proposed again from the same wording.';
const REMOVE_LINK = 'Remove this connection from your framework?';

function labelOf<T extends string>(options: { value: T; label: string }[], value: T): string {
  return options.find(option => option.value === value)?.label ?? value;
}

function failureText(error: unknown): string {
  if (error instanceof HttpError && error.status === 409) {
    return 'This changed. Review it again.';
  }
  return error instanceof Error ? error.message : 'That did not save.';
}

function RunSummary({ run }: { run: IdeaRun | null }) {
  if (!run) return null;
  const drops = DROP_LABEL.filter(([key]) => run.dropped[key] > 0)
    .map(([key, text]) => `${run.dropped[key]} ${text}`);
  return (
    <p role="status" style={{ fontSize: 13, color: 'var(--ink-3)' }}>
      {run.kind} · {run.status}. {run.itemsRead} read, {run.passesCompleted} of {run.passesPlanned} passes, {run.proposed} proposed.
      {drops.length > 0 && ` ${drops.join('; ')}.`}
      {run.status === 'partial' && ' Some of the read did not finish. Proposals already saved are still here.'}
      {run.status === 'failed' && ' The read did not finish.'}
    </p>
  );
}

function Selectors({
  position, domain, onPosition, onDomain,
}: {
  position: IdeaPosition;
  domain: IdeaDomain;
  onPosition: (value: IdeaPosition) => void;
  onDomain: (value: IdeaDomain) => void;
}) {
  const control: React.CSSProperties = {
    appearance: 'none',
    WebkitAppearance: 'none',
    background: 'var(--bg-0)',
    color: 'var(--ink)',
    border: '1px solid var(--line)',
    borderRadius: 8,
    padding: '8px 28px 8px 12px',
    fontFamily: 'var(--sans)',
    fontSize: 13,
    colorScheme: 'dark',
    backgroundImage: 'linear-gradient(45deg, transparent 50%, var(--ink-3) 50%), linear-gradient(135deg, var(--ink-3) 50%, transparent 50%)',
    backgroundPosition: 'right 12px center, right 7px center',
    backgroundSize: '5px 5px, 5px 5px',
    backgroundRepeat: 'no-repeat',
  };
  return (
    <div className="row" style={{ gap: 20, flexWrap: 'wrap' }}>
      <label className="col" style={{ gap: 6, minWidth: 160 }}>
        <span className="kicker">Position</span>
        <select style={control} value={position} onChange={event => onPosition(event.target.value as IdeaPosition)}>
          {POSITIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label className="col" style={{ gap: 6, minWidth: 160 }}>
        <span className="kicker">Domain</span>
        <select style={control} value={domain} onChange={event => onDomain(event.target.value as IdeaDomain)}>
          {DOMAINS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
    </div>
  );
}

function QuoteList({ citations }: { citations: IdeaCitation[] }) {
  const dated = citations.filter(citation => citation.entryDate);
  const undated = citations.filter(citation => !citation.entryDate);
  const quote = (citation: IdeaCitation) => (
    <blockquote key={citation.id} style={{ margin: 0, padding: '2px 0 2px 16px', borderLeft: '2px solid var(--sage-dim)' }}>
      <div className="serif ital" style={{ fontSize: 18, lineHeight: 1.45, color: 'var(--ink)' }}>"{citation.text}"</div>
      <div className="row" style={{ gap: 12, marginTop: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <span className="kicker">{STANCE_LABEL[citation.stance]}</span>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.06em', color: 'var(--ink-4)' }}>
          {citation.entryDate ? `Written on ${formatEventDate(citation.entryDate, DAY_LONG)}` : 'Undated'}
        </span>
        <Link to={`/journal?entry=${citation.entryId}`} style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--sage)', textDecoration: 'none' }}>
          Source
        </Link>
      </div>
    </blockquote>
  );
  return (
    <div className="col" style={{ gap: 12 }}>
      {dated.map(quote)}
      {undated.length > 0 && (
        <section className="col" style={{ gap: 12 }}>
          <h3 className="kicker">Undated</h3>
          {undated.map(quote)}
        </section>
      )}
    </div>
  );
}

function ReviewCard({ card }: { card: IdeasReview['ideas'][number] }) {
  const confirm = useConfirmIdea();
  const reject = useRejectIdea();
  const dismissQuotes = useRejectIdeaCitations();
  const [position, setPosition] = React.useState<IdeaPosition>(
    card.idea.status === 'active' ? card.idea.position : 'exploring',
  );
  const [domain, setDomain] = React.useState<IdeaDomain>(card.idea.domain);
  const ids = card.citations.map(citation => citation.id);
  const busy = confirm.isPending || reject.isPending || dismissQuotes.isPending;
  const error = confirm.error ?? reject.error ?? dismissQuotes.error;
  const isNew = card.idea.status === 'candidate';

  return (
    <article className="card col" style={{ gap: 22, padding: '28px 32px' }}>
      <div className="col" style={{ gap: 10, maxWidth: 680 }}>
        <div className="kicker">Iris restatement of your writing</div>
        <h3 className="serif" style={{ margin: 0, fontSize: 28, lineHeight: 1.15, letterSpacing: '-0.02em' }}>{card.idea.statement}</h3>
      </div>
      <div className="col" style={{ gap: 14, maxWidth: 680 }}>
        <div className="kicker">In your writing</div>
        <QuoteList citations={card.citations} />
      </div>
      {isNew && ids.length === 0 && (
        <p style={{ margin: 0, color: 'var(--ink-3)' }}>This proposal no longer has a valid quotation, so it cannot be added.</p>
      )}
      {error && <div role="alert">{failureText(error)}</div>}
      <hr className="hairline" />
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap' }}>
        <Selectors position={position} domain={domain} onPosition={setPosition} onDomain={setDomain} />
        <div className="row" style={{ gap: 8 }}>
          {isNew ? (
            <>
              <button className="btn" disabled={busy} onClick={() => reject.mutate(card.idea.id)}>Dismiss proposal</button>
              <button className="btn primary" disabled={busy || ids.length === 0} onClick={() => confirm.mutate({
                id: card.idea.id, body: { citationIds: ids, position, domain },
              })}>Add to framework</button>
            </>
          ) : (
            <>
              <button className="btn" disabled={busy} onClick={() => dismissQuotes.mutate({
                id: card.idea.id, citationIds: ids,
              })}>Dismiss new quotes</button>
              <button className="btn primary" disabled={busy} onClick={() => confirm.mutate({
                id: card.idea.id, body: { citationIds: ids, position, domain },
              })}>Accept new quotes</button>
            </>
          )}
        </div>
      </div>
    </article>
  );
}

function LinkCard({ link }: { link: IdeaLink }) {
  const confirm = useConfirmIdeaLink();
  const reject = useRejectIdeaLink();
  const busy = confirm.isPending || reject.isPending;
  const error = confirm.error ?? reject.error;
  return (
    <article className="card col" style={{ gap: 8, padding: 24 }}>
      <div className="kicker">Iris's proposal</div>
      <p>{link.fromStatement}</p>
      <div className="tag">{LINK_LABEL[link.kind]}</div>
      <p>{link.toStatement}</p>
      <p>{link.rationale}</p>
      <div className="row" style={{ gap: 8 }}>
        <Link to={`/ideas/${link.fromIdeaId}`}>From</Link>
        <Link to={`/ideas/${link.toIdeaId}`}>To</Link>
      </div>
      {error && <div role="alert">{failureText(error)}</div>}
      <div className="row" style={{ gap: 8 }}>
        {link.status === 'candidate' && (
          <button className="btn primary" disabled={busy} onClick={() => confirm.mutate(link.id)}>Accept</button>
        )}
        <button className="btn" disabled={busy} onClick={() => {
          if (link.status !== 'accepted' || window.confirm(REMOVE_LINK)) reject.mutate(link.id);
        }}>{link.status === 'accepted' ? 'Remove from framework' : 'Dismiss'}</button>
      </div>
    </article>
  );
}

function Discovery() {
  const discover = useDiscoverIdeas();
  return (
    <div className="col" style={{ gap: 8 }}>
      <button className="btn primary" disabled={discover.isPending} onClick={() => discover.mutate(undefined)}>
        {discover.isPending ? 'Reading…' : 'Read my reflections'}
      </button>
      <p>Sends eligible reflections to the configured model</p>
      {discover.error && <div role="alert">{failureText(discover.error)}</div>}
    </div>
  );
}

const plain: React.CSSProperties = { color: 'inherit', textDecoration: 'none' };
const field: React.CSSProperties = {
  background: 'var(--bg-2)', color: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 6,
  padding: '6px 10px', fontFamily: 'var(--sans)', fontSize: 13,
};
const LAYOUT_KEY = 'iris.ideas.layout';

function readLayout(): 'graph' | 'list' {
  try { return window.localStorage.getItem(LAYOUT_KEY) === 'list' ? 'list' : 'graph'; } catch { return 'graph'; }
}

function Toggle({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick}
      style={{ fontFamily: 'var(--mono)', fontSize: 11, padding: '4px 10px', borderRadius: 999, cursor: 'pointer',
               border: `1px solid ${on ? 'var(--sage)' : 'var(--line)'}`, background: on ? 'var(--sage)' : 'transparent',
               color: on ? '#14140f' : 'var(--ink-3)' }}>
      {children}
    </button>
  );
}

function FrameworkView({ data, waiting, review }: { data: IdeasFramework; waiting: number; review?: IdeasReview }) {
  const [query, setQuery] = React.useState('');
  const [domain, setDomain] = React.useState<IdeaDomain | ''>('');
  const [layout, setLayoutState] = React.useState(readLayout);
  const [areas, setAreas] = React.useState(true);
  const [proposals, setProposals] = React.useState(false);
  const setLayout = (value: 'graph' | 'list') => {
    setLayoutState(value);
    try { window.localStorage.setItem(LAYOUT_KEY, value); } catch { /* not remembered */ }
  };
  const byId = new Map(data.ideas.map(idea => [idea.id, idea]));
  const matches = (idea: IdeaSummary) => (
    idea.statement.toLowerCase().includes(query.trim().toLowerCase())
    && (domain === '' || idea.domain === domain)
  );
  const anchored = data.ideas.filter(idea => !idea.needsEvidence && matches(idea));
  const needing = data.ideas.filter(idea => idea.needsEvidence);
  const groups = DOMAINS.map(option => ({
    ...option,
    ideas: anchored.filter(idea => idea.domain === option.value),
  })).filter(group => group.ideas.length > 0);
  const tensions = data.links.filter(link => data.tensionIds.includes(link.id));
  const foundations = data.foundationIds.map(id => byId.get(id)).filter((idea): idea is IdeaSummary => !!idea);
  const unconnected = data.unconnectedIds.map(id => byId.get(id)).filter((idea): idea is IdeaSummary => !!idea && matches(idea));

  if (data.ideas.length === 0 && !(layout === 'graph' && proposals)) {
    return (
      <EmptyState
        title="No framework yet."
        body={waiting
          ? `${waiting} proposals are waiting in Review. Nothing is added until you accept the quotes.`
          : 'Read your reflections to propose ideas. Nothing is added until you accept the quotes.'}
        action={waiting
          ? <Link to="/ideas?view=review">Review proposals</Link>
          : <Link to="/journal">Journal</Link>}
      />
    );
  }

  const controls = (
    <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
      <Toggle on={layout === 'graph'} onClick={() => setLayout('graph')}>graph</Toggle>
      <Toggle on={layout === 'list'} onClick={() => setLayout('list')}>list</Toggle>
      <span style={{ width: 12 }} />
      <input aria-label="Search statements" placeholder="Search" value={query} style={field}
        onChange={event => setQuery(event.target.value)} />
      <select aria-label="Filter domain" value={domain} style={field}
        onChange={event => setDomain(event.target.value as IdeaDomain | '')}>
        <option value="">All domains</option>
        {DOMAINS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
      {layout === 'graph' && <>
        <Toggle on={areas} onClick={() => setAreas(a => !a)}>areas</Toggle>
        <Toggle on={proposals} onClick={() => setProposals(p => !p)}>
          proposals{review ? ` · ${review.ideas.length}` : ''}
        </Toggle>
      </>}
    </div>
  );

  if (layout === 'graph') {
    const shown = new Set(data.ideas.filter(matches).map(idea => idea.id));
    return (
      <div className="col" style={{ gap: 16 }}>
        {controls}
        <IdeaGraph
          ideas={data.ideas.filter(idea => shown.has(idea.id))}
          links={data.links}
          proposedIdeas={proposals ? (review?.ideas ?? []).map(card => card.idea).filter(matches) : []}
          proposedLinks={proposals ? review?.links ?? [] : []}
          showAreas={areas}
          areaLabel={value => labelOf(DOMAINS, value)}
        />
      </div>
    );
  }

  return (
    <div className="col" style={{ gap: 28 }}>
      {controls}
      {tensions.length > 0 && (
        <section className="col" style={{ gap: 8 }}>
          <h2 className="serif">Open tensions</h2>
          {tensions.map(link => (
            <article key={link.id} className="card" style={{ padding: 16 }}>
              <p><Link to={`/ideas/${link.fromIdeaId}`} style={plain}>{link.fromStatement}</Link></p>
              <div className="tag">{LINK_LABEL[link.kind]}</div>
              <p><Link to={`/ideas/${link.toIdeaId}`} style={plain}>{link.toStatement}</Link></p>
            </article>
          ))}
        </section>
      )}
      {foundations.length > 0 && (
        <section>
          <h2 className="serif">Ideas other arguments depend on</h2>
          {foundations.map(idea => <IdeaRow key={idea.id} idea={idea} />)}
        </section>
      )}
      {unconnected.length > 0 && (
        <section>
          <h2 className="serif">Unconnected</h2>
          {unconnected.map(idea => <IdeaRow key={idea.id} idea={idea} />)}
        </section>
      )}
      {groups.map(group => (
        <section key={group.value} className="col" style={{ gap: 8 }}>
          <h2 className="serif">{group.label}</h2>
          {group.ideas.map(idea => <IdeaRow key={idea.id} idea={idea} />)}
        </section>
      ))}
      {needing.length > 0 && (
        <section>
          <h2 className="serif">Needs source review</h2>
          {needing.map(idea => <IdeaRow key={idea.id} idea={idea} />)}
        </section>
      )}
    </div>
  );
}

function IdeaRow({ idea }: { idea: IdeaSummary }) {
  return (
    <Link to={`/ideas/${idea.id}`} className="card" style={{ ...plain, display: 'block', padding: 16 }}>
      <div className="kicker">{labelOf(POSITIONS, idea.position)} · {labelOf(DOMAINS, idea.domain)}</div>
      <div className="serif" style={{ fontSize: 19, color: 'var(--ink)', margin: '4px 0' }}>{idea.statement}</div>
      <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>{idea.citationCount - idea.undatedCount} dated · {idea.undatedCount} undated</div>
    </Link>
  );
}

function ReviewView({ data }: { data: IdeasReview }) {
  if (data.ideas.length === 0 && data.links.length === 0) {
    return <EmptyState title="Nothing waiting." body="Accepted ideas stay in the framework. New proposals and new quotes wait here." />;
  }
  return (
    <div className="col" style={{ gap: 20, maxWidth: 820 }}>
      {data.ideas.map(card => <ReviewCard key={card.idea.id} card={card} />)}
      {data.links.map(link => <LinkCard key={link.id} link={link} />)}
    </div>
  );
}

function IdeasIndex() {
  const [params, setParams] = useSearchParams();
  const review = params.get('view') === 'review';
  const framework = useIdeasFramework();
  const queue = useIdeaReview();
  const data = review ? queue : framework;
  return (
    <main className="col" style={{ gap: 28, padding: '40px 48px 72px', maxWidth: 980 }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div className="col" style={{ gap: 8 }}>
          <div className="kicker">ideas · positions in your writing</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 48, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
            {review ? <>Waiting<br /><span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>on you.</span></> : 'Ideas'}
          </h1>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn" onClick={() => setParams({})}>Framework</button>
          <button className="btn" onClick={() => setParams({ view: 'review' })}>Review</button>
        </div>
      </div>
      <Discovery />
      <RunSummary run={data.data?.lastRun ?? null} />
      {data.isLoading && <LoadingState label="Loading your framework…" />}
      {data.isError && <ErrorState onRetry={() => data.refetch()} />}
      {data.data && (review
        ? <ReviewView data={data.data as IdeasReview} />
        : <FrameworkView data={data.data as IdeasFramework} waiting={queue.data?.ideas.length ?? 0} review={queue.data} />)}
    </main>
  );
}

function CritiquePanel({ idea, critiques }: { idea: IdeaSummary; critiques: IdeaCritique[] }) {
  const critique = useCritiqueIdea();
  return (
    <section className="col" style={{ gap: 12 }}>
      <h2 className="serif">Iris sparring partner</h2>
      <button
        className="btn"
        disabled={critique.isPending || idea.needsEvidence}
        onClick={() => critique.mutate(idea.id)}
      >
        {critique.isPending ? 'Challenging…' : 'Challenge this idea'}
      </button>
      {idea.needsEvidence && <p>This idea has no valid quotation, so a new challenge is disabled.</p>}
      {critique.error && <div role="alert">{failureText(critique.error)}</div>}
      {critiques.map(item => <CritiqueCard key={item.id} critique={item} />)}
    </section>
  );
}

function CritiqueCard({ critique }: { critique: IdeaCritique }) {
  const empty = critique.content.objections.length === 0
    && critique.content.possiblePremises.length === 0
    && critique.content.relatedThought.length === 0;
  return (
    <article className="card col" style={{ gap: 8, padding: 16 }}>
      <div>Generated by Iris — not your recorded position</div>
      <div className="kicker">{formatEventDate(critique.createdAt)} · {critique.model}</div>
      {!critique.isCurrent && <span className="tag">Based on an earlier framework</span>}
      {empty && <p>No substantive challenge returned.</p>}
      {critique.content.objections.length > 0 && (
        <div>
          <h3>Objections</h3>
          {critique.content.objections.map((item, index) => (
            <p key={index}>{item.argument} {item.question} <Link to="/journal">Write a response</Link></p>
          ))}
        </div>
      )}
      {critique.content.possiblePremises.length > 0 && (
        <div>
          <h3>Possible premises</h3>
          {critique.content.possiblePremises.map((item, index) => (
            <p key={index}>{item.premise} {item.question} <Link to="/journal">Write a response</Link></p>
          ))}
        </div>
      )}
      {critique.content.relatedThought.length > 0 && (
        <div>
          <h3>Suggested connections — not source-verified</h3>
          {critique.content.relatedThought.map((item, index) => (
            <p key={index}>{item.name} ({item.kind}): {item.connection}</p>
          ))}
        </div>
      )}
    </article>
  );
}

function IdeaDetail({ id }: { id: string }) {
  const detail = useIdea(id);
  const update = useUpdateIdea();
  const reject = useRejectIdea();
  const links = useDiscoverIdeaLinks();
  const idea = detail.data?.idea;
  const [position, setPosition] = React.useState<IdeaPosition>('exploring');
  const [domain, setDomain] = React.useState<IdeaDomain>('other');
  React.useEffect(() => {
    if (!idea) return;
    setPosition(idea.position);
    setDomain(idea.domain);
  }, [idea]);

  if (detail.isLoading) return <LoadingState label="Loading this idea…" />;
  if (detail.isError || !detail.data || !idea) {
    return (
      <div className="col" style={{ gap: 12, padding: 28 }}>
        <ErrorState message="This idea is missing or no longer in your framework." onRetry={() => detail.refetch()} />
        <Link to="/ideas">Back to framework</Link>
      </div>
    );
  }
  const accepted = detail.data.links.filter(link => link.status === 'accepted');
  const pending = detail.data.citations.filter(citation => citation.status === 'candidate');
  const error = update.error ?? reject.error ?? links.error;

  return (
    <main className="col" style={{ gap: 20, padding: 28 }}>
      <Link to="/ideas">Framework</Link>
      <h1 className="serif">{idea.statement}</h1>
      <Selectors position={position} domain={domain} onPosition={setPosition} onDomain={setDomain} />
      <button className="btn" disabled={update.isPending} onClick={() => update.mutate({ id, body: { position, domain } })}>
        Save
      </button>
      {pending.length > 0 && <p>New quotations are waiting in review.</p>}
      <section>
        <h2 className="serif">Written on</h2>
        <QuoteList citations={detail.data.citations.filter(citation => citation.status === 'accepted')} />
      </section>
      <section className="col" style={{ gap: 8 }}>
        <h2 className="serif">Connections</h2>
        <button className="btn" disabled={links.isPending || idea.needsEvidence} onClick={() => links.mutate(id)}>
          {links.isPending ? 'Looking…' : 'Find connections'}
        </button>
        {idea.needsEvidence && <p>This idea has no valid quotation, so new connections are disabled.</p>}
        <IdeaNeighborhood idea={idea} links={accepted} />
        {detail.data.links.map(link => <LinkCard key={link.id} link={link} />)}
      </section>
      <CritiquePanel idea={idea} critiques={detail.data.critiques} />
      {error && <div role="alert">{failureText(error)}</div>}
      <button className="btn" disabled={reject.isPending} onClick={() => {
        if (window.confirm(REMOVE_IDEA)) reject.mutate(id);
      }}>Remove from framework</button>
    </main>
  );
}

export function IdeasScreen() {
  const { id } = useParams<{ id: string }>();
  return id ? <IdeaDetail key={id} id={id} /> : <IdeasIndex />;
}

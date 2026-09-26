import React from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { IdeaNeighborhood } from '@/components/IdeaNeighborhood';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { HttpError } from '@/api/client';
import {
  useConfirmIdea, useConfirmIdeaLink, useCritiqueIdea, useDiscoverIdeaLinks, useDiscoverIdeas,
  useDiscoverMeanings, useMeaningEstimate,
  useIdea, useIdeaReview, useIdeasFramework, useRejectIdea, useRejectIdeaCitations,
  useRejectIdeaLink, useUpdateIdea,
} from '@/hooks/useIdeas';
import { formatEventDate, DAY_LONG } from '@/lib/dates';
import { Badge, Button, ChoiceGroup, Page, Panel } from '@/ui';
import styles from './IdeasScreen.module.css';
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
  { value: 'life', label: 'Life' },
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
  same_meaning: 'means the same as',
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
    <p role="status" className={styles.muted}>
      {run.kind === 'meaning' ? 'same meaning' : run.kind} · {run.status}. {run.itemsRead} read, {run.passesCompleted} of {run.passesPlanned} passes, {run.proposed} proposed.
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
  return (
    <div className={styles.selectors}>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>Position</span>
        <select value={position} onChange={event => onPosition(event.target.value as IdeaPosition)}>
          {POSITIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>Area</span>
        <select aria-label="Domain" value={domain} onChange={event => onDomain(event.target.value as IdeaDomain)}>
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
    <blockquote key={citation.id} className={styles.quote}>
      <p className={styles.quoteText}>&ldquo;{citation.text}&rdquo;</p>
      <div className={styles.quoteMeta}>
        <span>{STANCE_LABEL[citation.stance]}</span>
        <span>{citation.entryDate ? `Written on ${formatEventDate(citation.entryDate, DAY_LONG)}` : 'Undated'}</span>
        <Link to={`/journal?entry=${citation.entryId}`}>Source</Link>
      </div>
    </blockquote>
  );
  return (
    <div className={styles.stack}>
      {dated.map(quote)}
      {undated.length > 0 && (
        <section className={styles.stack}>
          <h3 className={styles.minorTitle}>Undated</h3>
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
    <Panel as="article">
      <div className={styles.stack}>
        <Badge>Iris's restatement of your writing</Badge>
        <h3 className={styles.statement}>{card.idea.statement}</h3>
      </div>
      <div className={styles.stack}>
        <h4 className={styles.minorTitle}>In your writing</h4>
        <QuoteList citations={card.citations} />
      </div>
      {isNew && ids.length === 0 && (
        <p className={styles.muted}>This proposal no longer has a valid quotation, so it cannot be added.</p>
      )}
      {error && <div role="alert">{failureText(error)}</div>}
      <div className={styles.decide}>
        <Selectors position={position} domain={domain} onPosition={setPosition} onDomain={setDomain} />
        <div className={styles.row}>
          {isNew ? (
            <>
              <Button disabled={busy} onClick={() => reject.mutate(card.idea.id)}>Dismiss proposal</Button>
              <Button variant="primary" disabled={busy || ids.length === 0} onClick={() => confirm.mutate({
                id: card.idea.id, body: { citationIds: ids, position, domain },
              })}>Add to framework</Button>
            </>
          ) : (
            <>
              <Button disabled={busy} onClick={() => dismissQuotes.mutate({
                id: card.idea.id, citationIds: ids,
              })}>Dismiss new quotes</Button>
              <Button variant="primary" disabled={busy} onClick={() => confirm.mutate({
                id: card.idea.id, body: { citationIds: ids, position, domain },
              })}>Accept new quotes</Button>
            </>
          )}
        </div>
      </div>
    </Panel>
  );
}

function LinkCard({ link }: { link: IdeaLink }) {
  const confirm = useConfirmIdeaLink();
  const reject = useRejectIdeaLink();
  const busy = confirm.isPending || reject.isPending;
  const error = confirm.error ?? reject.error;
  return (
    <Panel as="article">
      <Badge>Iris's proposal</Badge>
      <p className={styles.linkEnd}>{link.fromStatement}</p>
      <Badge tone="action">{LINK_LABEL[link.kind]}</Badge>
      <p className={styles.linkEnd}>{link.toStatement}</p>
      <p className={styles.muted}>{link.rationale}</p>
      <div className={styles.row}>
        <Link to={`/ideas/${link.fromIdeaId}`}>From</Link>
        <Link to={`/ideas/${link.toIdeaId}`}>To</Link>
      </div>
      {error && <div role="alert">{failureText(error)}</div>}
      <div className={styles.row}>
        {link.status === 'candidate' && (
          <Button variant="primary" disabled={busy} onClick={() => confirm.mutate(link.id)}>Accept</Button>
        )}
        <Button disabled={busy} onClick={() => {
          if (link.status !== 'accepted' || window.confirm(REMOVE_LINK)) reject.mutate(link.id);
        }}>{link.status === 'accepted' ? 'Remove from framework' : 'Dismiss'}</Button>
      </div>
    </Panel>
  );
}

function Discovery() {
  const discover = useDiscoverIdeas();
  return (
    <div className={styles.stack}>
      <Button variant="primary" disabled={discover.isPending} onClick={() => discover.mutate(undefined)}>
        {discover.isPending ? 'Reading…' : 'Read my reflections'}
      </Button>
      <p>Sends eligible reflections to the configured model</p>
      {discover.error && <div role="alert">{failureText(discover.error)}</div>}
      <SameMeaning />
    </div>
  );
}

/**
 * Finding ideas that share one meaning. Asking shows what would be sent and
 * what it would cost; nothing leaves until the owner presses Send.
 */
function SameMeaning() {
  const [asking, setAsking] = React.useState(false);
  const estimate = useMeaningEstimate(asking);
  const find = useDiscoverMeanings();
  if (!asking) {
    return (
      <div className={styles.row}>
        <Button onClick={() => setAsking(true)} disabled={find.isPending}>
          {find.isPending ? 'Finding…' : 'Find ideas with the same meaning'}
        </Button>
        {find.error && <span role="alert">{failureText(find.error)}</span>}
      </div>
    );
  }
  const e = estimate.data;
  return (
    <div role="dialog" aria-label="Find ideas with the same meaning" className={styles.ask}>
      {estimate.isPending && <span>Counting…</span>}
      {estimate.isError && <span role="alert">The estimate did not load.</span>}
      {e && (e.calls === 0
        ? <span>You need at least two accepted ideas to compare.</span>
        : <span>
            Sends your {e.ideas} accepted idea statements, and no journal text, to the model in {e.calls} call{e.calls > 1 ? 's' : ''}: {e.estimate}.
            Pairs it finds wait in Review; nothing is linked until you accept it.
          </span>)}
      <div className={styles.row}>
        <Button variant="primary" disabled={!e || e.calls === 0}
          onClick={() => { setAsking(false); find.mutate(undefined); }}>Send</Button>
        <Button onClick={() => setAsking(false)}>Cancel</Button>
      </div>
    </div>
  );
}

const LAYOUT_KEY = 'iris.ideas.layout';

function readLayout(): 'graph' | 'list' {
  try { return window.localStorage.getItem(LAYOUT_KEY) === 'list' ? 'list' : 'graph'; } catch { return 'graph'; }
}

// three.js is large; only a visit to the graph loads it.
const IdeaGraph = React.lazy(() => import('@/components/IdeaGraph').then(m => ({ default: m.IdeaGraph })));

function Toggle({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick} className={styles.toggle}>{children}</button>
  );
}

/** Gives its child the height from where it starts to the bottom of the window. */
function FullHeight({ children }: { children: (height: number) => React.ReactNode }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [height, setHeight] = React.useState(640);
  React.useEffect(() => {
    const measure = () => {
      const top = ref.current?.getBoundingClientRect().top ?? 0;
      setHeight(Math.max(480, Math.round(window.innerHeight - top - 64)));
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, []);
  return <div ref={ref}>{children(height)}</div>;
}

function FrameworkView({ data, waiting, review }: { data: IdeasFramework; waiting: number; review?: IdeasReview }) {
  const [query, setQuery] = React.useState('');
  const [domain, setDomain] = React.useState<IdeaDomain | ''>('');
  const [layout, setLayoutState] = React.useState(readLayout);
  // Off by default: ideas float and cluster by their links, as in Obsidian.
  const [areas, setAreas] = React.useState(false);
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
    <div className={styles.controls}>
      <Toggle on={layout === 'graph'} onClick={() => setLayout('graph')}>Graph</Toggle>
      <Toggle on={layout === 'list'} onClick={() => setLayout('list')}>List</Toggle>
      <span className={styles.gap} />
      <input aria-label="Search statements" placeholder="Search" value={query}
        onChange={event => setQuery(event.target.value)} />
      <select aria-label="Filter domain" value={domain}
        onChange={event => setDomain(event.target.value as IdeaDomain | '')}>
        <option value="">All domains</option>
        {DOMAINS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
      {layout === 'graph' && <>
        <Toggle on={areas} onClick={() => setAreas(a => !a)}>Areas</Toggle>
        <Toggle on={proposals} onClick={() => setProposals(p => !p)}>
          Proposals{review ? ` (${review.ideas.length})` : ''}
        </Toggle>
      </>}
    </div>
  );

  if (layout === 'graph') {
    const shown = new Set(data.ideas.filter(matches).map(idea => idea.id));
    return (
      <div className={styles.stack}>
        {controls}
        <FullHeight>{height => <React.Suspense fallback={<LoadingState label="Drawing your ideas…" />}><IdeaGraph height={height}
          ideas={data.ideas.filter(idea => shown.has(idea.id))}
          links={data.links}
          proposedIdeas={proposals ? (review?.ideas ?? []).map(card => card.idea).filter(matches) : []}
          proposedLinks={proposals ? review?.links ?? [] : []}
          showAreas={areas}
          areaLabel={value => labelOf(DOMAINS, value)}
        /></React.Suspense>}</FullHeight>
      </div>
    );
  }

  return (
    <div className={styles.listView}>
      {controls}
      {tensions.length > 0 && (
        <section className={styles.stack}>
          <h2 className={styles.sectionTitle}>Open tensions</h2>
          {tensions.map(link => (
            <Panel key={link.id} as="article">
              <Link to={`/ideas/${link.fromIdeaId}`} className={styles.linkEnd}>{link.fromStatement}</Link>
              <Badge tone="worse">{LINK_LABEL[link.kind]}</Badge>
              <Link to={`/ideas/${link.toIdeaId}`} className={styles.linkEnd}>{link.toStatement}</Link>
            </Panel>
          ))}
        </section>
      )}
      {foundations.length > 0 && (
        <section className={styles.stack}>
          <h2 className={styles.sectionTitle}>Ideas other arguments depend on</h2>
          {foundations.map(idea => <IdeaRow key={idea.id} idea={idea} />)}
        </section>
      )}
      {unconnected.length > 0 && (
        <section className={styles.stack}>
          <h2 className={styles.sectionTitle}>Unconnected</h2>
          {unconnected.map(idea => <IdeaRow key={idea.id} idea={idea} />)}
        </section>
      )}
      {groups.map(group => (
        <section key={group.value} className={styles.stack}>
          <h2 className={styles.sectionTitle}>{group.label}</h2>
          {group.ideas.map(idea => <IdeaRow key={idea.id} idea={idea} />)}
        </section>
      ))}
      {needing.length > 0 && (
        <section className={styles.stack}>
          <h2 className={styles.sectionTitle}>Needs source review</h2>
          {needing.map(idea => <IdeaRow key={idea.id} idea={idea} />)}
        </section>
      )}
    </div>
  );
}

function IdeaRow({ idea }: { idea: IdeaSummary }) {
  return (
    <Link to={`/ideas/${idea.id}`} className={styles.ideaRow}>
      <span className={styles.ideaMeta}>
        <Badge tone={idea.domain === 'life' ? 'confirmed' : 'neutral'}>{labelOf(DOMAINS, idea.domain)}</Badge>
        {labelOf(POSITIONS, idea.position)}
      </span>
      <span className={styles.ideaStatement}>{idea.statement}</span>
      <span className={styles.muted}>Written {idea.citationCount} {idea.citationCount === 1 ? 'time' : 'times'}{idea.undatedCount ? `, ${idea.undatedCount} undated` : ''}</span>
    </Link>
  );
}

function ReviewView({ data }: { data: IdeasReview }) {
  if (data.ideas.length === 0 && data.links.length === 0) {
    return <EmptyState title="Nothing waiting." body="Accepted ideas stay in the framework. New proposals and new quotes wait here." />;
  }
  return (
    <div className={styles.reviewList}>
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
    <Page title={review ? 'Waiting on you' : 'Ideas'} width="wide"
      description={review ? 'Proposals and new quotes. Nothing joins your framework until you accept it.' : 'Positions in your writing, and how they connect.'}
      actions={<ChoiceGroup label="Ideas view" value={review ? 'review' : 'framework'}
        options={[{ value: 'framework', label: 'Framework' }, { value: 'review', label: 'Review' }]}
        onChange={value => setParams(value === 'review' ? { view: 'review' } : {})} />}>
      <div className={styles.discovery}><Discovery /></div>
      <RunSummary run={data.data?.lastRun ?? null} />
      {data.isLoading && <LoadingState label="Loading your framework…" />}
      {data.isError && <ErrorState onRetry={() => data.refetch()} />}
      {data.data && (review
        ? <ReviewView data={data.data as IdeasReview} />
        : <FrameworkView data={data.data as IdeasFramework} waiting={queue.data?.ideas.length ?? 0} review={queue.data} />)}
    </Page>
  );
}

function CritiquePanel({ idea, critiques }: { idea: IdeaSummary; critiques: IdeaCritique[] }) {
  const critique = useCritiqueIdea();
  return (
    <section className={styles.stack}>
      <h2 className={styles.sectionTitle}>Iris sparring partner</h2>
      <div><Button disabled={critique.isPending || idea.needsEvidence} onClick={() => critique.mutate(idea.id)}>
        {critique.isPending ? 'Challenging…' : 'Challenge this idea'}
      </Button></div>
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
    <Panel as="article">
      <div>Generated by Iris — not your recorded position</div>
      <p className={styles.muted}>{formatEventDate(critique.createdAt)}, {critique.model}</p>
      {!critique.isCurrent && <Badge>Based on an earlier framework</Badge>}
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
    </Panel>
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
      <div className={styles.stack}>
        <ErrorState message="This idea is missing or no longer in your framework." onRetry={() => detail.refetch()} />
        <Link to="/ideas">Back to framework</Link>
      </div>
    );
  }
  const accepted = detail.data.links.filter(link => link.status === 'accepted');
  const pending = detail.data.citations.filter(citation => citation.status === 'candidate');
  const error = update.error ?? reject.error ?? links.error;

  return (
    <Page width="standard" title={idea.statement}
      lead={<span className={styles.detailLead}><Link to="/ideas">All ideas</Link>
        <Badge tone={idea.domain === 'life' ? 'confirmed' : 'neutral'}>{labelOf(DOMAINS, idea.domain)}</Badge>
        {labelOf(POSITIONS, idea.position)}</span>}>
      <div className={styles.decide}>
        <Selectors position={position} domain={domain} onPosition={setPosition} onDomain={setDomain} />
        <Button disabled={update.isPending} onClick={() => update.mutate({ id, body: { position, domain } })}>Save</Button>
      </div>
      {pending.length > 0 && <p className={styles.muted}>New quotations are waiting in review.</p>}
      <section className={styles.stack}>
        <h2 className={styles.sectionTitle}>Written on</h2>
        <QuoteList citations={detail.data.citations.filter(citation => citation.status === 'accepted')} />
      </section>
      <section className={styles.stack}>
        <h2 className={styles.sectionTitle}>Connections</h2>
        <div><Button disabled={links.isPending || idea.needsEvidence} onClick={() => links.mutate(id)}>
          {links.isPending ? 'Looking…' : 'Find connections'}
        </Button></div>
        {idea.needsEvidence && <p className={styles.muted}>This idea has no valid quotation, so new connections are disabled.</p>}
        <IdeaNeighborhood idea={idea} links={accepted} />
        {detail.data.links.map(link => <LinkCard key={link.id} link={link} />)}
      </section>
      <CritiquePanel idea={idea} critiques={detail.data.critiques} />
      {error && <div role="alert">{failureText(error)}</div>}
      <div><Button variant="danger" disabled={reject.isPending} onClick={() => {
        if (window.confirm(REMOVE_IDEA)) reject.mutate(id);
      }}>Remove from framework</Button></div>
    </Page>
  );
}

export function IdeasScreen() {
  const { id } = useParams<{ id: string }>();
  return id ? <IdeaDetail key={id} id={id} /> : <IdeasIndex />;
}

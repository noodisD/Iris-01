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
import { AREA_COLOR, AREAS, areaLabel } from '@/lib/ideaAreas';
import { LINK_COLOR, LINK_KINDS, LINK_LABEL, SYMMETRIC } from '@/lib/ideaLinks';
import { Badge, Button, Page, Panel, Section, Tabs, TabPanel } from '@/ui';
import styles from './IdeasScreen.module.css';
import type {
  IdeaCitation, IdeaCritique, IdeaDomain, IdeaLink, IdeaPosition, IdeaRun, IdeaSummary,
  IdeasFramework, IdeasReview, LinkKind,
} from '@/types/api';

const POSITIONS: { value: IdeaPosition; label: string }[] = [
  { value: 'exploring', label: 'Exploring' },
  { value: 'endorsed', label: 'I hold this' },
  { value: 'opposed', label: 'I reject this' },
];
const DOMAINS = AREAS;
const STANCE_LABEL: Record<IdeaCitation['stance'], string> = {
  endorsed: 'You endorsed this then',
  questioned: 'You questioned this then',
  opposed: 'You opposed this then',
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

const RUN_NAME: Record<IdeaRun['kind'], string> = {
  discovery: 'Reading your reflections',
  links: 'Finding connections',
  meaning: 'Finding related ideas',
};

/** The last thing IRIS was asked to do, and how it went, in words. */
function RunSummary({ run }: { run: IdeaRun | null }) {
  if (!run) return null;
  const drops = DROP_LABEL.filter(([key]) => run.dropped[key] > 0)
    .map(([key, text]) => `${run.dropped[key]} left out because ${text}`);
  const outcome = run.status === 'running' ? 'still running'
    : run.status === 'failed' ? 'did not finish'
    : `${run.proposed === 0 ? 'nothing new' : `${run.proposed} proposed`}${run.status === 'partial' ? ', but part of it did not finish; what was found is here' : ''}`;
  return (
    <p role="status" className={styles.muted}>
      Last time: {RUN_NAME[run.kind]}, {formatEventDate(run.startedAt)}: {outcome}.
      {drops.length > 0 && ` ${drops.join('; ')}.`}
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

function QuoteList({ citations, fold }: { citations: IdeaCitation[]; fold?: number }) {
  const [open, setOpen] = React.useState(false);
  const hidden = fold && !open ? Math.max(0, citations.length - fold) : 0;
  const visible = hidden ? citations.slice(0, fold) : citations;
  const dated = visible.filter(citation => citation.entryDate);
  const undated = visible.filter(citation => !citation.entryDate);
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
      {hidden > 0 && (
        <div><Button variant="quiet" size="sm" onClick={() => setOpen(true)}>
          Show {hidden} more {hidden === 1 ? 'quote' : 'quotes'}
        </Button></div>
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
      <h3 className={styles.statement}>{card.idea.statement}</h3>
      <div className={styles.stack}>
        <h4 className={styles.minorTitle}>
          {card.citations.length === 1 ? 'In your writing' : `In your writing, ${card.citations.length} times`}
        </h4>
        <QuoteList citations={card.citations} fold={2} />
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
  const proposal = link.status === 'candidate';
  // IRIS proposes a relation; the owner may name a more exact one, and say
  // which idea is which, before accepting.
  const [kind, setKind] = React.useState<LinkKind>(link.kind);
  const [reverse, setReverse] = React.useState(false);
  const flipped = reverse && !SYMMETRIC.has(kind);
  const from = flipped ? { id: link.toIdeaId, text: link.toStatement } : { id: link.fromIdeaId, text: link.fromStatement };
  const to = flipped ? { id: link.fromIdeaId, text: link.fromStatement } : { id: link.toIdeaId, text: link.toStatement };
  const changed = kind !== link.kind || flipped;
  return (
    <Panel as="article" aria-label={`${link.fromStatement} ${LINK_LABEL[link.kind]} ${link.toStatement}`}>
      <Link to={`/ideas/${from.id}`} className={styles.linkEnd}>{from.text}</Link>
      {proposal ? (
        <div className={styles.relation}>
          <select aria-label="Relation" value={kind} disabled={busy}
            onChange={e => setKind(e.target.value as LinkKind)}>
            {LINK_KINDS.map(k => <option key={k} value={k}>{LINK_LABEL[k]}</option>)}
          </select>
          {!SYMMETRIC.has(kind) && (
            <Button size="sm" variant="quiet" disabled={busy} onClick={() => setReverse(r => !r)}>
              Swap the two ideas
            </Button>
          )}
        </div>
      ) : <Badge tone="action">{LINK_LABEL[link.kind]}</Badge>}
      <Link to={`/ideas/${to.id}`} className={styles.linkEnd}>{to.text}</Link>
      <p className={styles.muted}>{link.rationale}</p>
      {error && <div role="alert">{failureText(error)}</div>}
      <div className={styles.row}>
        {proposal && (
          <Button variant="primary" disabled={busy}
            onClick={() => confirm.mutate({ id: link.id, as: changed ? { kind, reverse: flipped } : undefined })}>
            {changed ? 'Accept with this relation' : 'Accept'}
          </Button>
        )}
        <Button disabled={busy} onClick={() => {
          if (link.status !== 'accepted' || window.confirm(REMOVE_LINK)) reject.mutate(link.id);
        }}>{link.status === 'accepted' ? 'Remove from framework' : 'Dismiss'}</Button>
      </div>
    </Panel>
  );
}

/**
 * Asking IRIS to look again. Both send something to the model, so each says
 * what; they live beside the proposals they produce, not above the framework.
 */
function AskIris({ run }: { run: IdeaRun | null }) {
  const discover = useDiscoverIdeas();
  return (
    <Section title="Ask IRIS to look again">
      <div className={styles.asks}>
        <div className={styles.ask}>
          <div>
            <Button disabled={discover.isPending} onClick={() => discover.mutate(undefined)}>
              {discover.isPending ? 'Reading…' : 'Read my reflections'}
            </Button>
          </div>
          <p className={styles.muted}>Looks through your journal for positions you state and proposes them here, with the quotes. Sends eligible entries to the model.</p>
          {discover.error && <p role="alert" className={styles.error}>{failureText(discover.error)}</p>}
        </div>
        <RelatedIdeas />
      </div>
      <RunSummary run={run} />
    </Section>
  );
}

/**
 * Finding ideas that mean the same or apply one another. Asking shows what
 * would be sent and what it would cost; nothing leaves until the owner presses Send.
 */
function RelatedIdeas() {
  const [asking, setAsking] = React.useState(false);
  const estimate = useMeaningEstimate(asking);
  const find = useDiscoverMeanings();
  const e = estimate.data;
  return (
    <div className={styles.ask}>
      <div>
        <Button onClick={() => setAsking(true)} disabled={find.isPending || asking}>
          {find.isPending ? 'Finding…' : 'Find related ideas'}
        </Button>
      </div>
      <p className={styles.muted}>Compares your accepted ideas for ones that mean the same, or where one applies another. Sends only the idea statements.</p>
      {find.error && <p role="alert" className={styles.error}>{failureText(find.error)}</p>}
      {asking && (
        <div role="dialog" aria-label="Find related ideas" className={styles.confirmSend}>
          {estimate.isPending && <p className={styles.muted}>Counting…</p>}
          {estimate.isError && <p role="alert" className={styles.error}>The estimate did not load.</p>}
          {e && (e.calls === 0
            ? <p>You need at least two accepted ideas to compare.</p>
            : <p>
                Sends your {e.ideas} accepted idea statements, and no journal text, to the model in {e.calls} call{e.calls > 1 ? 's' : ''}: {e.estimate}.
                Pairs it finds wait in Review; nothing is linked until you accept it.
              </p>)}
          <div className={styles.row}>
            <Button variant="primary" disabled={!e || e.calls === 0}
              onClick={() => { setAsking(false); find.mutate(undefined); }}>Send</Button>
            <Button variant="quiet" onClick={() => setAsking(false)}>Cancel</Button>
          </div>
        </div>
      )}
    </div>
  );
}

type View = 'map' | 'list' | 'review';
const VIEW_KEY = 'iris.ideas.layout';

function rememberedView(): 'map' | 'list' {
  try { return window.localStorage.getItem(VIEW_KEY) === 'list' ? 'list' : 'map'; } catch { return 'map'; }
}

// three.js is large; only a visit to the map loads it.
const IdeaGraph = React.lazy(() => import('@/components/IdeaGraph').then(m => ({ default: m.IdeaGraph })));

/** The height from where the map starts to the bottom of the window. */
function useFillHeight(ref: React.RefObject<HTMLElement | null>) {
  const [height, setHeight] = React.useState(600);
  React.useEffect(() => {
    const measure = () => {
      const top = ref.current?.getBoundingClientRect().top ?? 0;
      const narrow = window.innerWidth < 900;
      setHeight(narrow
        ? Math.max(360, Math.round(window.innerHeight * 0.62))
        : Math.max(460, Math.round(window.innerHeight - top - 40)));
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [ref]);
  return height;
}

interface Filter { query: string; area: IdeaDomain | null }

function matches(idea: IdeaSummary, filter: Filter): boolean {
  return idea.statement.toLowerCase().includes(filter.query.trim().toLowerCase())
    && (filter.area === null || idea.domain === filter.area);
}

/** Search, and the areas as chips: the map's colour key and its filter in one. */
function Filters({ ideas, filter, onChange }: { ideas: IdeaSummary[]; filter: Filter; onChange: (f: Filter) => void }) {
  const counts = new Map<IdeaDomain, number>();
  ideas.forEach(idea => counts.set(idea.domain, (counts.get(idea.domain) ?? 0) + 1));
  return (
    <div className={styles.filters}>
      <input type="search" aria-label="Search your ideas" placeholder="Search your ideas" value={filter.query}
        className={styles.search} onChange={event => onChange({ ...filter, query: event.target.value })} />
      <div className={styles.chips} role="group" aria-label="Areas">
        {AREAS.filter(area => counts.has(area.value)).map(area => (
          <button key={area.value} type="button" className={styles.chip}
            aria-pressed={filter.area === area.value}
            onClick={() => onChange({ ...filter, area: filter.area === area.value ? null : area.value })}>
            <span className={styles.dot} style={{ background: AREA_COLOR[area.value] }} aria-hidden="true" />
            {area.label}
            <span className={styles.count}>{counts.get(area.value)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function connectionsOf(data: IdeasFramework): Map<string, number> {
  const out = new Map<string, number>();
  data.links.filter(link => link.status === 'accepted').forEach(link => {
    out.set(link.fromIdeaId, (out.get(link.fromIdeaId) ?? 0) + 1);
    out.set(link.toIdeaId, (out.get(link.toIdeaId) ?? 0) + 1);
  });
  return out;
}

function byArea(ideas: IdeaSummary[]) {
  return AREAS.map(area => ({ ...area, ideas: ideas.filter(idea => idea.domain === area.value) }))
    .filter(group => group.ideas.length > 0);
}

function MapView({ data, review, filter, onFilter }: {
  data: IdeasFramework; review?: IdeasReview; filter: Filter; onFilter: (f: Filter) => void;
}) {
  const canvas = React.useRef<HTMLDivElement>(null);
  const height = useFillHeight(canvas);
  const [areas, setAreas] = React.useState(false);
  const [proposals, setProposals] = React.useState(false);
  const [focus, setFocus] = React.useState<string | null>(null);
  const shown = data.ideas.filter(idea => matches(idea, filter));
  const kinds = LINK_KINDS.filter(kind => data.links.some(link => link.kind === kind && link.status === 'accepted'));
  const waiting = review?.ideas.filter(card => card.idea.status === 'candidate').length ?? 0;

  return (
    <div className={styles.stack}>
      <Filters ideas={data.ideas} filter={filter} onChange={onFilter} />
      <div className={styles.map}>
        <div className={styles.canvas} ref={canvas}>
          <React.Suspense fallback={<LoadingState label="Drawing your ideas…" />}>
            <IdeaGraph height={height} focusId={focus}
              ideas={shown}
              links={data.links}
              proposedIdeas={proposals ? (review?.ideas ?? []).map(card => card.idea).filter(idea => matches(idea, filter)) : []}
              proposedLinks={proposals ? review?.links ?? [] : []}
              showAreas={areas}
              areaLabel={areaLabel}
            />
          </React.Suspense>
          <div className={styles.mapTools}>
            <button type="button" className={styles.chip} aria-pressed={areas} onClick={() => setAreas(a => !a)}>
              Group by area
            </button>
            {waiting > 0 && (
              <button type="button" className={styles.chip} aria-pressed={proposals} onClick={() => setProposals(p => !p)}>
                Show proposals ({waiting})
              </button>
            )}
          </div>
          <div className={styles.legend}>
            {kinds.map(kind => (
              <span key={kind} className={styles.legendItem}>
                <span className={styles.legendLine} style={{ background: LINK_COLOR[kind] }} aria-hidden="true" />
                {LINK_LABEL[kind]}
              </span>
            ))}
            <span className={styles.legendHint}>Drag to turn, scroll to zoom, click an idea to open it</span>
          </div>
        </div>
        <nav className={styles.index} aria-label="Ideas on the map" style={{ maxHeight: height }}>
          {shown.length === 0 && <p className={styles.muted}>No idea matches.</p>}
          {byArea(shown).map(group => (
            <section key={group.value} className={styles.indexGroup}>
              <h2 className={styles.indexArea}>
                <span className={styles.dot} style={{ background: AREA_COLOR[group.value] }} aria-hidden="true" />
                {group.label}
              </h2>
              <ul className={styles.indexList}>
                {group.ideas.map(idea => (
                  <li key={idea.id}>
                    <Link to={`/ideas/${idea.id}`} className={styles.indexItem}
                      onMouseEnter={() => setFocus(idea.id)} onMouseLeave={() => setFocus(null)}
                      onFocus={() => setFocus(idea.id)} onBlur={() => setFocus(null)}>
                      <span className={styles.clamp}>{idea.statement}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </nav>
      </div>
    </div>
  );
}

function ListView({ data, filter, onFilter }: { data: IdeasFramework; filter: Filter; onFilter: (f: Filter) => void }) {
  const connections = connectionsOf(data);
  const foundations = new Set(data.foundationIds);
  const anchored = data.ideas.filter(idea => !idea.needsEvidence && matches(idea, filter));
  const needing = data.ideas.filter(idea => idea.needsEvidence && matches(idea, filter));
  const tensions = data.links.filter(link => data.tensionIds.includes(link.id));
  const row = (idea: IdeaSummary) => (
    <IdeaRow key={idea.id} idea={idea} connections={connections.get(idea.id) ?? 0} foundation={foundations.has(idea.id)} />
  );
  return (
    <div className={styles.listView}>
      <Filters ideas={data.ideas} filter={filter} onChange={onFilter} />
      {tensions.length > 0 && (
        <section className={styles.stack} aria-labelledby="tensions">
          <h2 id="tensions" className={styles.sectionTitle}>Open tensions</h2>
          <p className={styles.muted}>Two ideas you hold that cannot both be true in the same conditions.</p>
          {tensions.map(link => (
            <Panel key={link.id} as="article" className={styles.tension}>
              <Link to={`/ideas/${link.fromIdeaId}`} className={styles.linkEnd}>{link.fromStatement}</Link>
              <span className={styles.relationWord}>{LINK_LABEL[link.kind]}</span>
              <Link to={`/ideas/${link.toIdeaId}`} className={styles.linkEnd}>{link.toStatement}</Link>
            </Panel>
          ))}
        </section>
      )}
      {anchored.length === 0 && needing.length === 0 && <p className={styles.muted}>No idea matches.</p>}
      {byArea(anchored).map(group => (
        <section key={group.value} className={styles.areaGroup} aria-labelledby={`area-${group.value}`}>
          <h2 id={`area-${group.value}`} className={styles.areaTitle}>
            <span className={styles.dot} style={{ background: AREA_COLOR[group.value] }} aria-hidden="true" />
            {group.label}
            <span className={styles.count}>{group.ideas.length}</span>
          </h2>
          <ul className={styles.rows}>{group.ideas.map(row)}</ul>
        </section>
      ))}
      {needing.length > 0 && (
        <section className={styles.areaGroup} aria-labelledby="needing">
          <h2 id="needing" className={styles.areaTitle}>Needs its quotes checked</h2>
          <p className={styles.muted}>The entries these rest on have changed or gone. Open one to see what is left.</p>
          <ul className={styles.rows}>{needing.map(row)}</ul>
        </section>
      )}
    </div>
  );
}

function IdeaRow({ idea, connections, foundation }: { idea: IdeaSummary; connections: number; foundation: boolean }) {
  const facts = [
    labelOf(POSITIONS, idea.position),
    `written ${idea.citationCount} ${idea.citationCount === 1 ? 'time' : 'times'}${idea.undatedCount ? `, ${idea.undatedCount} undated` : ''}`,
    connections ? `${connections} ${connections === 1 ? 'connection' : 'connections'}` : null,
  ].filter(Boolean).join(', ');
  return (
    <li>
      <Link to={`/ideas/${idea.id}`} className={styles.ideaRow}>
        <span className={styles.ideaStatement}>{idea.statement}</span>
        <span className={styles.ideaMeta}>
          {facts.charAt(0).toUpperCase() + facts.slice(1)}
          {foundation && <Badge>Others depend on this</Badge>}
        </span>
      </Link>
    </li>
  );
}

function ReviewView({ data }: { data: IdeasReview }) {
  const links = data.links.filter(link => link.status === 'candidate');
  const fresh = data.ideas.filter(card => card.idea.status === 'candidate');
  const quotes = data.ideas.filter(card => card.idea.status !== 'candidate');
  return (
    <div className={styles.reviewList}>
      {links.length + fresh.length + quotes.length === 0 && (
        <p className={styles.empty}>Nothing is waiting. Ask IRIS to look again below, or keep writing.</p>
      )}
      {links.length > 0 && (
        <Section title={`Connections to judge (${links.length})`}
          description="How two of your accepted ideas relate. Change the relation if IRIS has it wrong.">
          {links.map(link => <LinkCard key={link.id} link={link} />)}
        </Section>
      )}
      {fresh.length > 0 && (
        <Section title={`New ideas from your writing (${fresh.length})`}
          description="IRIS's wording of a position you state, with the quotes it rests on.">
          {fresh.map(card => <ReviewCard key={card.idea.id} card={card} />)}
        </Section>
      )}
      {quotes.length > 0 && (
        <Section title={`New quotes for ideas you hold (${quotes.length})`}>
          {quotes.map(card => <ReviewCard key={card.idea.id} card={card} />)}
        </Section>
      )}
      <AskIris run={data.lastRun} />
    </div>
  );
}

function IdeasIndex() {
  const [params, setParams] = useSearchParams();
  const asked = params.get('view');
  const view: View = asked === 'review' || asked === 'list' || asked === 'map' ? asked : rememberedView();
  const [filter, setFilter] = React.useState<Filter>({ query: '', area: null });
  const framework = useIdeasFramework();
  const queue = useIdeaReview();
  const waiting = (queue.data?.ideas.length ?? 0) + (queue.data?.links.filter(link => link.status === 'candidate').length ?? 0);
  const show = (next: View) => {
    if (next !== 'review') { try { window.localStorage.setItem(VIEW_KEY, next); } catch { /* not remembered */ } }
    setParams(next === 'map' ? {} : { view: next });
  };
  const framed = (body: (data: IdeasFramework) => React.ReactNode) => (
    framework.isLoading ? <LoadingState label="Loading your ideas…" />
      : framework.isError || !framework.data ? <ErrorState onRetry={() => framework.refetch()} />
      : framework.data.ideas.length === 0 ? (
        <EmptyState title="No ideas yet."
          body={waiting
            ? `${waiting} proposals are waiting in Review. Nothing is added until you accept it.`
            : 'Ask IRIS to read your reflections in Review. Nothing is added until you accept it.'} />
      ) : body(framework.data)
  );
  return (
    <Page title="Ideas" width="wide"
      description="The positions you hold, in your own words, and how they connect.">
      <Tabs<View> label="Ideas" value={view} onChange={show}
        tabs={[
          { value: 'map', label: 'Map' },
          { value: 'list', label: 'List' },
          { value: 'review', label: waiting ? `Review (${waiting})` : 'Review' },
        ]}>
        <TabPanel value="map">{framed(data => <MapView data={data} review={queue.data} filter={filter} onFilter={setFilter} />)}</TabPanel>
        <TabPanel value="list">{framed(data => <ListView data={data} filter={filter} onFilter={setFilter} />)}</TabPanel>
        <TabPanel value="review">
          {queue.isLoading ? <LoadingState label="Loading what is waiting…" />
            : queue.isError || !queue.data ? <ErrorState onRetry={() => queue.refetch()} />
            : <ReviewView data={queue.data} />}
        </TabPanel>
      </Tabs>
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
      lead={<span className={styles.detailLead}><Link to="/ideas">← All ideas</Link>
        <span className={styles.row}>
          <span className={styles.dot} style={{ background: AREA_COLOR[idea.domain] }} aria-hidden="true" />
          {labelOf(DOMAINS, idea.domain)}
        </span>
        {labelOf(POSITIONS, idea.position)}</span>}>
      <div className={`${styles.decide} ${styles.detailDecide}`}>
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

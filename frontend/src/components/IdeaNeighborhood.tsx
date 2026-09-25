import { Link } from 'react-router-dom';
import type { IdeaLink, IdeaSummary } from '@/types/api';

const KIND_LABEL: Record<IdeaLink['kind'], string> = {
  supports: 'supports',
  contradicts: 'contradicts',
  refines: 'refines',
  depends_on: 'depends on',
};

function cut(statement: string): string {
  return statement.length > 42 ? statement.slice(0, 42) : statement;
}

export function IdeaNeighborhood({ idea, links }: { idea: IdeaSummary; links: IdeaLink[] }) {
  const accepted = links.filter(link => link.status === 'accepted' && (
    link.fromIdeaId === idea.id || link.toIdeaId === idea.id
  ));
  const neighbourIds = [...new Set(accepted.flatMap(link => (
    link.fromIdeaId === idea.id ? [link.toIdeaId] : [link.fromIdeaId]
  )))].sort((a, b) => Number(a) - Number(b));

  return (
    <div className="col" style={{ gap: 16 }}>
      <svg viewBox="0 0 640 420" width="100%" role="group" aria-label="Accepted connections">
        <defs>
          <marker id="idea-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto-start-reverse">
            <path d="M0,0 L7,3 L0,6 Z" fill="var(--ink-3)" />
          </marker>
        </defs>
        <circle cx={320} cy={210} r={28} fill="var(--bg-2)" stroke="var(--sage)" />
        <text x={320} y={214} textAnchor="middle" fontSize={11} fill="var(--ink)">
          {cut(idea.statement)}
        </text>
        {neighbourIds.length === 0 && (
          <text x={320} y={270} textAnchor="middle" fontSize={13} fill="var(--ink-3)">
            No accepted connections yet.
          </text>
        )}
        {neighbourIds.map((id, index) => {
          const angle = (-90 + (index * 360) / neighbourIds.length) * Math.PI / 180;
          const ux = Math.cos(angle);
          const uy = Math.sin(angle);
          const x = 320 + 150 * ux;
          const y = 210 + 150 * uy;
          const pair = accepted.filter(link => link.fromIdeaId === id || link.toIdeaId === id);
          const statement = pair[0].fromIdeaId === id ? pair[0].fromStatement : pair[0].toStatement;
          const directed = pair.filter(link => link.kind !== 'contradicts');
          const outward = directed.some(link => link.fromIdeaId === idea.id);
          const inward = directed.some(link => link.toIdeaId === idea.id);
          const markerEnd = outward ? 'url(#idea-arrow)' : undefined;
          const markerStart = inward ? 'url(#idea-arrow)' : undefined;
          return (
            <g key={id}>
              <line
                x1={320 + 28 * ux} y1={210 + 28 * uy} x2={x - 22 * ux} y2={y - 22 * uy}
                stroke="var(--ink-3)"
                markerEnd={markerEnd}
                markerStart={markerStart}
              />
              <text x={(320 + x) / 2} y={(210 + y) / 2} fontSize={10} fill="var(--ink-2)">
                {pair.map(link => KIND_LABEL[link.kind]).join(' · ')}
              </text>
              <Link to={`/ideas/${id}`} aria-label={statement}>
                <circle cx={x} cy={y} r={22} fill="var(--bg-2)" stroke="var(--line)" />
                <text x={x} y={y + 4} textAnchor="middle" fontSize={10} fill="var(--ink)">
                  {cut(statement)}
                </text>
              </Link>
            </g>
          );
        })}
      </svg>
      <ul className="col" style={{ gap: 10, padding: 0, listStyle: 'none' }}>
        {accepted.map(link => {
          const fromIsCurrent = link.fromIdeaId === idea.id;
          const neighbourId = fromIsCurrent ? link.toIdeaId : link.fromIdeaId;
          const neighbourStatement = fromIsCurrent ? link.toStatement : link.fromStatement;
          const neighbour = <Link to={`/ideas/${neighbourId}`}>{neighbourStatement}</Link>;
          return (
            <li key={link.id}>
              <p>{fromIsCurrent ? idea.statement : neighbour} <span className="kicker">{KIND_LABEL[link.kind]}</span> {fromIsCurrent ? neighbour : idea.statement}</p>
              <p>{link.rationale}</p>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

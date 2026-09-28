import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { ObsIOPart, ObsInvocationDetail } from '@/api/observatory';
import { ErrorState } from '@/components/states';
import { Button, Section } from '@/ui';
import styles from './InvocationDetail.module.css';

export function InvocationDetail({
  detail, error, onRetry, onSelect, limitNote,
}: {
  detail: ObsInvocationDetail | undefined;
  error?: string;
  onRetry?: () => void;
  onSelect?: (traceId: string, spanId: string) => void;
  limitNote?: string;
}) {
  if (error) {
    return (
      <div className={styles.detail}>
        <ErrorState message={error} onRetry={onRetry} />
      </div>
    );
  }
  if (!detail) return <div className={styles.detail}><p role="status">Loading invocation…</p></div>;
  const span = detail.span;
  return (
    <div className={styles.detail}>
      <Section title={span.name} description={`${span.component}, ${span.status}${span.status_message ? `, ${span.status_message}` : ''}`}>
        {limitNote && <p role="status">{limitNote}</p>}
        <p>
          <Link to={`/observatory/traces/${span.trace_id}?span=${span.span_id}`}>Open trace</Link>
          {' '}
          <Link to={`/observatory?view=system&component=${encodeURIComponent(span.component)}&module=${encodeURIComponent(span.module_id ?? span.name)}&call_trace=${span.trace_id}&span=${span.span_id}`}>Show on system map</Link>
        </p>
        <div className={styles.io}>
          <IOList title="Inputs" parts={detail.io.inputs} waiting={false} />
          <IOList title="Outputs" parts={detail.io.outputs} waiting={span.status === 'running'} />
        </div>
        {detail.events.length > 0 && (
          <div>
            <h3>Events</h3>
            {detail.events.map((event, index) => <p key={`${event.name}-${index}`}>{event.name} {event.at}</p>)}
          </div>
        )}
        {detail.logs.length > 0 && (
          <div>
            <h3>Logs</h3>
            {detail.logs.map((log, index) => <p key={`${log.at}-${index}`}>{log.level} {log.message}</p>)}
          </div>
        )}
        {detail.related.length > 0 && (
          <div>
            <h3>Related invocations</h3>
            <ul>
              {detail.related.map(item => (
                <li key={`${item.trace_id}:${item.span_id}`}>
                  <Button variant="quiet" size="sm" onClick={() => onSelect?.(item.trace_id, item.span_id)}>
                    {item.name} {item.trace_id.slice(0, 8)} {item.span_id.slice(0, 8)}
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}
        <RawAttributes attributes={detail.attributes} />
      </Section>
    </div>
  );
}

function IOList({ title, parts, waiting }: { title: string; parts: ObsIOPart[]; waiting: boolean }) {
  return (
    <div>
      <h3>{title}</h3>
      {waiting && parts.length === 0 && <p>Waiting for output.</p>}
      {parts.map(part => <IOPartView key={part.label} part={part} waiting={waiting && part.state === 'pending'} />)}
      {!waiting && parts.length === 0 && <p>Not captured for this invocation.</p>}
    </div>
  );
}

function IOPartView({ part, waiting }: { part: ObsIOPart; waiting: boolean }) {
  const [shown, setShown] = useState(false);
  const text = part.text ?? '';
  const preview = text.slice(0, 1000);
  const parsed = part.format === 'json' && part.state === 'captured' && part.truncated !== true && part.partial !== true
    ? tryParse(text)
    : undefined;
  return (
    <div>
      <strong>{part.label}</strong>
      <p>
        {waiting || part.state === 'pending' ? 'Waiting for output.' : null}
        {part.state === 'not_captured' ? 'Not captured for this invocation.' : null}
        {part.state === 'metadata_only' ? 'Metadata only.' : null}
        {part.truncated ? ' Truncated.' : null}
        {part.partial ? ' Partial.' : null}
        {part.reason ? ` ${part.reason}` : null}
      </p>
      {parsed !== undefined ? <JsonTree value={parsed} /> : part.state === 'captured' && (
        <>
          <p className={styles.wrap}>{shown ? text : preview}{!shown && text.length > 1000 ? '…' : ''}</p>
          {text.length > 1000 && <Button variant="quiet" size="sm" onClick={() => setShown(value => !value)}>{shown ? 'Hide captured text' : 'Show captured text'}</Button>}
          <Button variant="quiet" size="sm" onClick={() => { void navigator.clipboard?.writeText(text); }}>Copy captured text</Button>
        </>
      )}
    </div>
  );
}

function tryParse(text: string): unknown | undefined {
  if (!text) return text;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}

function JsonTree({ value }: { value: unknown }) {
  const [open, setOpen] = useState(false);
  const [limit, setLimit] = useState(50);
  if (value == null || typeof value !== 'object') {
    return <p className={styles.wrap}>{value === null ? 'null' : String(value)}</p>;
  }
  const entries = Array.isArray(value) ? value.map((item, index) => [String(index), item] as const) : Object.entries(value);
  return (
    <div>
      <Button variant="quiet" size="sm" onClick={() => setOpen(value => !value)}>{open ? 'Hide' : 'Show'} {Array.isArray(value) ? 'list' : 'object'} ({entries.length})</Button>
      {open && entries.slice(0, limit).map(([key, child]) => (
        <div key={key} className={styles.nest}>
          <span>{key}</span>
          <JsonTree value={child} />
        </div>
      ))}
      {open && entries.length > limit && <Button variant="quiet" size="sm" onClick={() => setLimit(value => value + 50)}>Show more</Button>}
    </div>
  );
}

function RawAttributes({ attributes }: { attributes: Record<string, unknown> }) {
  const [open, setOpen] = useState<string | null>(null);
  const entries = Object.entries(attributes).sort(([a], [b]) => a.localeCompare(b));
  if (entries.length === 0) return null;
  return (
    <div>
      <h3>Attributes</h3>
      {entries.map(([key, value]) => {
        const text = typeof value === 'string' ? value : JSON.stringify(value);
        const long = text.length > 200 || text.includes('\n');
        return (
          <div key={key}>
            <strong>{key}</strong>{' '}
            {long
              ? <Button variant="quiet" size="sm" onClick={() => setOpen(open === key ? null : key)}>{open === key ? 'Hide' : 'Show'}</Button>
              : <span className={styles.wrap}>{text}</span>}
            {open === key && <p className={styles.wrap}>{text}</p>}
          </div>
        );
      })}
    </div>
  );
}

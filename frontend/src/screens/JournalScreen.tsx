import React from 'react';
import { useJournal } from '@/hooks/useData';
import { createEntry } from '@/api/journal';
import { LoadingState, ErrorState } from '@/components/states';
import { useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';

const PROMPTS = ['What happened today?', 'What were you feeling?', 'What do you want Iris to remember?'];

export function JournalScreen() {
  const { data, isLoading, isError, refetch } = useJournal();
  const qc = useQueryClient();
  const [lines, setLines] = React.useState(['', '', '']);
  const [energy, setEnergy] = React.useState(6);
  const [saving, setSaving] = React.useState(false);

  if (isLoading) return <LoadingState label="Iris is opening your journal…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  const save = async () => {
    setSaving(true);
    try {
      await createEntry({ lines: lines.filter(Boolean), energy });
      setLines(['', '', '']);
      qc.invalidateQueries({ queryKey: qk.journal });
    } finally { setSaving(false); }
  };

  return (
    <div className="row" style={{ height: '100%' }}>
      <div className="col" style={{ flex: 1, padding: '32px 56px 40px', minWidth: 0, overflow: 'auto' }}>
        <div className="row" style={{ alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 28 }}>
          <div className="col" style={{ gap: 6 }}>
            <div className="kicker">today · evening</div>
            <h1 className="serif" style={{ margin: 0, fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
              Three lines,<br /><span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>please.</span>
            </h1>
          </div>
          <div className="col gap-8" style={{ alignItems: 'flex-end' }}>
            <span className="kicker">how is today?</span>
            <div className="row" style={{ gap: 4 }}>
              {[1,2,3,4,5,6,7,8,9,10].map(n => (
                <button key={n} onClick={() => setEnergy(n)} style={{ width: 22, height: 22, borderRadius: '50%', border: `1px solid ${n === energy ? 'var(--sage)' : 'var(--line)'}`, background: n === energy ? 'var(--sage)' : 'transparent', color: n === energy ? '#14140f' : 'var(--ink-3)', fontFamily: 'var(--mono)', fontSize: 10, cursor: 'pointer', padding: 0 }}>{n}</button>
              ))}
            </div>
          </div>
        </div>

        <div className="col" style={{ gap: 8, maxWidth: 720 }}>
          {PROMPTS.map((prompt, i) => (
            <div key={i} className="col" style={{ gap: 4, padding: '14px 0', borderBottom: '1px solid var(--line)' }}>
              <div className="row" style={{ alignItems: 'baseline', gap: 12 }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', letterSpacing: '0.1em', textTransform: 'uppercase', minWidth: 16 }}>0{i+1}</span>
                <span className="serif ital" style={{ fontSize: 18, color: 'var(--ink-3)' }}>{prompt}</span>
              </div>
              <textarea value={lines[i]} onChange={e => { const c = [...lines]; c[i] = e.target.value; setLines(c); }} rows={2}
                style={{ background: 'transparent', border: 'none', resize: 'none', outline: 'none', color: 'var(--ink)', fontFamily: 'var(--serif)', fontSize: 20, lineHeight: 1.5, padding: '4px 0 4px 28px' }} />
            </div>
          ))}
        </div>

        <div className="row" style={{ gap: 8, marginTop: 18, maxWidth: 720, justifyContent: 'flex-end' }}>
          <button className="btn primary" onClick={save} disabled={saving || !lines.some(Boolean)}>{saving ? 'Saving…' : 'Save entry'}</button>
        </div>
      </div>

      <aside style={{ width: 380, flexShrink: 0, borderLeft: '1px dashed var(--line)', padding: '32px 28px', overflow: 'auto' }}>
        <div className="kicker" style={{ marginBottom: 8 }}>recent entries</div>
        <h3 className="serif" style={{ margin: '0 0 22px', fontSize: 24, lineHeight: 1 }}>{data.entries.length} recent</h3>
        <div className="col" style={{ gap: 22 }}>
          {data.entries.map((e) => (
            <article key={e.id} className="col" style={{ gap: 6 }}>
              <div className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between' }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{new Date(e.createdAt).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</span>
                <div className="row" style={{ gap: 4 }}>{(e.tags ?? []).map(t => <span key={t} style={{ fontSize: 9, fontFamily: 'var(--mono)', color: 'var(--ink-4)' }}>·{t}</span>)}</div>
              </div>
              <div style={{ fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.55 }}>{e.lines.join(' ')}</div>
              {e.irisNote && (
                <div className="row" style={{ gap: 6, alignItems: 'flex-start', marginTop: 4, paddingLeft: 10, borderLeft: '1px solid var(--sage-dim)' }}>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--sage)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>iris:</span>
                  <span style={{ fontSize: 11, color: 'var(--ink-2)', fontStyle: 'italic' }}>{e.irisNote}</span>
                </div>
              )}
            </article>
          ))}
        </div>

        {data.recurringPhrases && (
          <>
            <hr className="dotline" style={{ margin: '28px 0 18px' }} />
            <div className="kicker" style={{ marginBottom: 10 }}>phrases iris keeps hearing</div>
            <div className="col" style={{ gap: 6 }}>
              {data.recurringPhrases.map((p, i) => (
                <div key={i} className="row" style={{ alignItems: 'baseline', gap: 10 }}>
                  <span style={{ flex: 1, fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: 14, color: 'var(--ink)' }}>"{p.phrase}"</span>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)' }}>×{p.count}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </aside>
    </div>
  );
}

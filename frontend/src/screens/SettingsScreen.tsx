import React from 'react';
import { useUser, useConnectors, useKnowledge } from '@/hooks/useData';
import { setConnectorState } from '@/api/settings';
import { LoadingState, ErrorState } from '@/components/states';
import { useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import type { DataConnector } from '@/types/api';

export function SettingsScreen() {
  const { data: user } = useUser();
  const { data: connectors, isLoading, isError, refetch } = useConnectors();
  const { data: facts } = useKnowledge();
  const qc = useQueryClient();

  if (isLoading) return <LoadingState label="Iris is gathering what she knows…" />;
  if (isError || !connectors) return <ErrorState onRetry={() => refetch()} />;

  const cycle = async (c: DataConnector) => {
    const next = c.state === 'connected' ? 'pause' : c.state === 'paused' ? 'disconnect' : 'connect';
    await setConnectorState(c.id, next);
    qc.invalidateQueries({ queryKey: qk.connectors });
  };

  return (
    <div className="col" style={{ padding: '32px 56px 48px', gap: 28 }}>
      <header className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid var(--line)', paddingBottom: 18 }}>
        <div className="col" style={{ gap: 6 }}>
          <div className="kicker">settings · what iris knows</div>
          <h1 className="serif" style={{ margin: 0, fontSize: 56, lineHeight: 0.95, letterSpacing: '-0.025em' }}>
            The shape of you,<br /><span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>so far.</span>
          </h1>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn">export everything</button>
          <button className="btn" style={{ color: 'var(--rose)', borderColor: 'var(--rose)' }}>delete & forget</button>
        </div>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 32 }}>
        <section className="col" style={{ gap: 16 }}>
          <div className="kicker">iris's stable notes about you</div>
          <div className="col" style={{ gap: 4 }}>
            {(facts ?? []).map((k, i) => (
              <div key={k.id} style={{ display: 'grid', gridTemplateColumns: '1fr 80px 60px', gap: 16, padding: '14px 0', alignItems: 'baseline', borderTop: i === 0 ? 'none' : '1px solid var(--line-soft)' }}>
                <span className="serif" style={{ fontSize: 17, lineHeight: 1.4, color: 'var(--ink)', fontStyle: 'italic' }}>"{k.fact}"</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)' }}>{k.source}</span>
                <div className="row" style={{ gap: 6, justifyContent: 'flex-end' }}>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)' }}>{k.ageDays}d</span>
                  {k.editable && <button className="btn ghost" style={{ fontSize: 11, color: 'var(--rose)' }} aria-label="forget">×</button>}
                </div>
              </div>
            ))}
          </div>
        </section>

        <aside className="col" style={{ gap: 24 }}>
          <section>
            <div className="kicker">data sources · where iris looks</div>
            <div className="col" style={{ gap: 8, marginTop: 10 }}>
              {connectors.map((s) => (
                <div key={s.id} className="row" style={{ alignItems: 'center', gap: 14, padding: '10px 12px', background: s.featured ? 'rgba(169,200,163,0.06)' : 'var(--bg-2)', border: `1px solid ${s.featured ? 'var(--sage-dim)' : 'var(--line-soft)'}`, borderRadius: 8 }}>
                  <div className="col" style={{ flex: 1, gap: 1 }}>
                    <span style={{ fontSize: 13, color: 'var(--ink)' }}>{s.name}{s.featured && <span style={{ marginLeft: 8, fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--sage)', letterSpacing: '0.1em' }}>PRIMARY</span>}</span>
                    <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>{s.scopeDescription}</span>
                  </div>
                  <button onClick={() => cycle(s)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: s.state === 'connected' ? 'var(--sage)' : s.state === 'paused' ? 'var(--amber)' : 'var(--ink-4)' }}>
                    {s.state === 'connected' ? '● on' : s.state === 'paused' ? '◐ paused' : '○ off'}
                  </button>
                </div>
              ))}
            </div>
          </section>

          <section style={{ padding: '16px 18px', border: '1px solid var(--line-soft)', borderRadius: 10, background: 'var(--bg-2)' }}>
            <div className="row" style={{ gap: 10, alignItems: 'center', marginBottom: 8 }}>
              <div className="iris-orb sm" />
              <span className="kicker">iris's note</span>
            </div>
            <div className="serif ital" style={{ fontSize: 15, lineHeight: 1.4, color: 'var(--ink-2)' }}>
              "Everything I know about you lives on this device. If you ever want me to forget — half, or all — that is a button. Not a conversation."
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

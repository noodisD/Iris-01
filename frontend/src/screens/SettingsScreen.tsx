import React from 'react';
import { useUser, useConnectors, useKnowledge, useAnalysisPreferences } from '@/hooks/useData';
import { forgetFact, updateAnalysisPreferences, resetAnalysisPreferences } from '@/api/settings';
import { LoadingState, ErrorState } from '@/components/states';
import { useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';

/** Engine names as a person would describe what each one watches for. */
const ENGINE_LABELS: Record<string, string> = {
  persistence: 'patterns that keep returning',
  trajectory: 'whether something is growing or fading',
  tension: 'themes pulling in different directions',
  resolution: 'whether a pattern has settled',
  leverage: 'what tends to come before what',
  decision_impact: 'what changed after a decision',
};

export function SettingsScreen() {
  const { data: user } = useUser();
  const { data: connectors, isLoading, isError, refetch } = useConnectors();
  const { data: facts } = useKnowledge();
  const { data: analysis } = useAnalysisPreferences();
  const qc = useQueryClient();

  if (isLoading) return <LoadingState label="Iris is gathering what she knows…" />;
  if (isError || !connectors) return <ErrorState onRetry={() => refetch()} />;

  const forget = async (id: string) => {
    await forgetFact(id);
    qc.invalidateQueries({ queryKey: qk.knowledge });
  };

  // Changing a gate changes what Iris will say next, so invalidate the things
  // that were filtered through it as well as the settings themselves.
  const afterGateChange = () => {
    qc.invalidateQueries({ queryKey: qk.analysis });
    qc.invalidateQueries({ queryKey: qk.insights });
  };

  const setGate = async (patch: Parameters<typeof updateAnalysisPreferences>[0]) => {
    await updateAnalysisPreferences(patch);
    afterGateChange();
  };

  const toggleEngine = async (engine: string) => {
    if (!analysis) return;
    // null means "all engines"; the first toggle has to make that explicit
    // before one can be removed from it.
    const current = analysis.enabledEngines ?? analysis.availableEngines;
    const next = current.includes(engine)
      ? current.filter((e) => e !== engine)
      : [...current, engine];
    await setGate({ enabledEngines: next });
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
                  {k.editable && <button className="btn ghost" style={{ fontSize: 11, color: 'var(--rose)' }} aria-label="forget" onClick={() => forget(k.id)}>×</button>}
                </div>
              </div>
            ))}
          </div>
        </section>

        <aside className="col" style={{ gap: 24 }}>
          <section>
            <div className="kicker">data sources · not yet available</div>
            <div className="col" style={{ gap: 8, marginTop: 10 }}>
              {connectors.map((s) => (
                <div key={s.id} className="row" style={{ alignItems: 'center', gap: 14, padding: '10px 12px', background: s.featured ? 'rgba(169,200,163,0.06)' : 'var(--bg-2)', border: `1px solid ${s.featured ? 'var(--sage-dim)' : 'var(--line-soft)'}`, borderRadius: 8 }}>
                  <div className="col" style={{ flex: 1, gap: 1 }}>
                    <span style={{ fontSize: 13, color: 'var(--ink)' }}>{s.name}{s.featured && <span style={{ marginLeft: 8, fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--sage)', letterSpacing: '0.1em' }}>PRIMARY</span>}</span>
                    <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>{s.scopeDescription}</span>
                  </div>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-4)' }}>
                    not yet built
                  </span>
                </div>
              ))}
            </div>
          </section>

          {analysis && (
            <section className="col" style={{ gap: 12 }}>
              <div className="kicker">what iris is willing to say</div>
              <p style={{ fontSize: 11.5, lineHeight: 1.5, color: 'var(--ink-3)', margin: 0, fontStyle: 'italic' }}>
                These decide which observations reach a conversation at all. They
                are not about tone — a finding held back here is one Iris does not
                consider well-enough evidenced to raise.
              </p>

              <div className="col" style={{ gap: 6 }}>
                <label className="kicker" htmlFor="min-confidence">minimum confidence</label>
                <div className="row" style={{ gap: 6 }} id="min-confidence">
                  {(['low', 'medium', 'high'] as const).map((level) => (
                    <button
                      key={level}
                      className="btn ghost"
                      aria-pressed={analysis.minConfidence === level}
                      onClick={() => setGate({ minConfidence: level })}
                      style={{
                        flex: 1, fontFamily: 'var(--mono)', fontSize: 10,
                        letterSpacing: '0.08em', textTransform: 'uppercase',
                        padding: '7px 0', borderRadius: 6,
                        border: `1px solid ${analysis.minConfidence === level ? 'var(--sage)' : 'var(--line-soft)'}`,
                        background: analysis.minConfidence === level ? 'rgba(169,200,163,0.10)' : 'transparent',
                        color: analysis.minConfidence === level ? 'var(--sage)' : 'var(--ink-3)',
                      }}
                    >
                      {level}
                    </button>
                  ))}
                </div>
              </div>

              <div className="col" style={{ gap: 6 }}>
                <label className="kicker" htmlFor="max-items">
                  most observations at once · {analysis.maxItems}
                </label>
                <input
                  id="max-items"
                  type="range"
                  min={1}
                  max={10}
                  value={analysis.maxItems}
                  onChange={(e) => setGate({ maxItems: Number(e.target.value) })}
                  style={{ width: '100%', accentColor: 'var(--sage)' }}
                />
              </div>

              <div className="col" style={{ gap: 6 }}>
                <span className="kicker">what she looks for</span>
                <div className="col" style={{ gap: 2 }}>
                  {analysis.availableEngines.map((engine) => {
                    const on = (analysis.enabledEngines ?? analysis.availableEngines).includes(engine);
                    return (
                      <label key={engine} className="row" style={{ gap: 9, alignItems: 'center', cursor: 'pointer', padding: '3px 0' }}>
                        <input
                          type="checkbox"
                          checked={on}
                          onChange={() => toggleEngine(engine)}
                          style={{ accentColor: 'var(--sage)' }}
                        />
                        <span style={{ fontSize: 12.5, color: on ? 'var(--ink)' : 'var(--ink-4)' }}>
                          {ENGINE_LABELS[engine] ?? engine}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>

              <button
                className="btn ghost"
                onClick={async () => { await resetAnalysisPreferences(); afterGateChange(); }}
                style={{ alignSelf: 'flex-start', fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-4)' }}
              >
                restore defaults
              </button>
            </section>
          )}

          <section style={{ padding: '16px 18px', border: '1px solid var(--line-soft)', borderRadius: 10, background: 'var(--bg-2)' }}>
            <div className="row" style={{ gap: 10, alignItems: 'center', marginBottom: 8 }}>
              <div className="iris-orb sm" />
              <span className="kicker">iris's note</span>
            </div>
            <div className="serif ital" style={{ fontSize: 15, lineHeight: 1.4, color: 'var(--ink-2)' }}>
              "Everything I know about you is stored on this machine, in your own Postgres — nothing is kept anywhere else. What you write is sent to OpenAI to be turned into embeddings and replies, and nowhere else. Every note above is something I inferred from your own words; remove any of them with the ×, and it's gone."
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

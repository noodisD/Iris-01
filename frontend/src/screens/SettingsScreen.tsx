import React from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useKnowledge, useAnalysisPreferences } from '@/hooks/useData';
import { forgetFact, updateAnalysisPreferences, resetAnalysisPreferences, getMobileConnection, pairMobile, unpairMobile, phonePairingCode } from '@/api/settings';
import { LoadingState, ErrorState } from '@/components/states';
import { QrCode } from '@/components/QrCode';
import { qk } from '@/lib/queryClient';

/** Engine names as a person would describe what each one watches for. */
const ENGINE_LABELS: Record<string, string> = {
  trajectory: 'whether something is growing or fading',
  tension: 'themes pulling in different directions',
  resolution: 'whether a pattern has settled',
  leverage: 'what tends to come before what',
  decision_impact: 'what changed after a decision',
  lifelong: 'how often something recurred across the whole record',
  observations: 'what reading your entries noticed',
};

const TABS = [
  { id: 'conversation', label: 'Conversation' },
  { id: 'phone', label: 'Phone' },
  { id: 'notes', label: 'Notes' },
  { id: 'data', label: 'Your data' },
] as const;

const small: React.CSSProperties = { margin: 0, fontSize: 12.5, lineHeight: 1.55, color: 'var(--ink-3)' };

/** One topic: a title, a sentence on what it is for, then its controls. */
function Section({ title, hint, children }: { title: string; hint?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section aria-label={title} className="col" style={{ gap: 14, padding: '20px 22px', border: '1px solid var(--line-soft)',
                                                         borderRadius: 10, background: 'var(--bg-1)' }}>
      <div className="col" style={{ gap: 4 }}>
        <h2 className="serif" style={{ margin: 0, fontSize: 22, fontWeight: 400, color: 'var(--ink)' }}>{title}</h2>
        {hint && <p style={small}>{hint}</p>}
      </div>
      {children}
    </section>
  );
}

/** A labelled line in a list of facts about a connection. */
function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr', gap: 12, fontSize: 13, alignItems: 'baseline' }}>
      <span className="kicker">{label}</span>
      <span style={{ color: 'var(--ink-2)' }}>{children}</span>
    </div>
  );
}

function when(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString() : 'never';
}

export function SettingsScreen() {
  const { data: facts, isLoading, isError, refetch } = useKnowledge();
  const { data: analysis } = useAnalysisPreferences();
  const [maxItems, setMaxItems] = React.useState<number | null>(null);
  const qc = useQueryClient();
  const { data: mobile, error: connectionError } = useQuery({
    queryKey: qk.mobileConnection, queryFn: getMobileConnection, refetchInterval: 15_000,
  });
  const [mobileError, setMobileError] = React.useState('');
  const [newToken, setNewToken] = React.useState<string | null>(null);
  const [mobileBusy, setMobileBusy] = React.useState(false);
  const [showAddress, setShowAddress] = React.useState(false);
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find(t => t.id === params.get('tab')) ?? TABS[0]).id;


  const generatePairing = async () => {
    if (mobile?.paired && !window.confirm(
      'Replace the pairing token? The phone stops delivering until you scan the new pairing code.'
    )) return;
    const bytes = crypto.getRandomValues(new Uint8Array(32));
    const token = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
    setMobileBusy(true);
    setMobileError('');
    try {
      await pairMobile(token);
      setNewToken(token);
      await qc.invalidateQueries({ queryKey: qk.mobileConnection });
    } catch (error) {
      setMobileError(error instanceof Error ? error.message : String(error));
    } finally {
      setMobileBusy(false);
    }
  };

  const revokePairing = async () => {
    if (!window.confirm('Disconnect the Android collector? It will stop delivering new readings.')) return;
    setMobileBusy(true);
    setMobileError('');
    try {
      await unpairMobile();
      setNewToken(null);
      await qc.invalidateQueries({ queryKey: qk.mobileConnection });
    } catch (error) {
      setMobileError(error instanceof Error ? error.message : String(error));
    } finally {
      setMobileBusy(false);
    }
  };

  if (isLoading) return <LoadingState label="Iris is gathering what she knows…" />;
  if (isError || !facts) return <ErrorState onRetry={() => refetch()} />;

  // A cluster is found by the machine and can be found again. A confirmed
  // pattern is the owner's decision: forgetting it stops it being counted and
  // it will not be proposed again, so it asks first.
  const forget = async (id: string, source: string) => {
    if (source === 'confirmed' &&
        !window.confirm('Stop counting this confirmed pattern? Its occurrences are removed and it will not be proposed again.')) {
      return;
    }
    await forgetFact(id);
    qc.invalidateQueries({ queryKey: qk.knowledge });
  };

  // Changing a gate changes what Iris will say next, so invalidate the things
  // that were filtered through it as well as the settings themselves.
  const afterGateChange = () => {
    qc.invalidateQueries({ queryKey: qk.analysis });
  };

  const setGate = async (patch: Parameters<typeof updateAnalysisPreferences>[0]) => {
    await updateAnalysisPreferences(patch);
    afterGateChange();
  };

  const commitMaxItems = async () => {
    if (maxItems === null || !analysis || maxItems === analysis.maxItems) return;
    await setGate({ maxItems });
    setMaxItems(null);
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

  const phoneStatus = !mobile
    ? { tone: 'var(--ink-3)', text: connectionError ? 'Could not check the phone connection' : 'Checking the phone connection…' }
    : mobile.listener !== 'listening'
      ? { tone: 'var(--amber)', text: 'The phone listener is not running' }
      : mobile.paired
        ? { tone: 'var(--sage)', text: mobile.last_seen_at ? 'Phone paired and in touch' : 'Phone paired, not heard from yet' }
        : { tone: 'var(--ink-2)', text: 'No phone paired' };

  return (
    <div className="col" style={{ padding: '32px 56px 56px', gap: 24, maxWidth: 920 }}>
      <header className="col" style={{ gap: 6 }}>
        <div className="kicker">settings</div>
        <h1 className="serif" style={{ margin: 0, fontSize: 44, lineHeight: 1, letterSpacing: '-0.02em' }}>
          The shape of you, <span style={{ fontStyle: 'italic', color: 'var(--sage)' }}>so far.</span>
        </h1>
      </header>

      <nav role="tablist" aria-label="Settings" className="row" style={{ gap: 4, borderBottom: '1px solid var(--line)' }}>
        {TABS.map(t => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setParams({ tab: t.id })}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '10px 14px', marginBottom: -1,
                     fontFamily: 'var(--sans)', fontSize: 13, color: tab === t.id ? 'var(--ink)' : 'var(--ink-3)',
                     borderBottom: `2px solid ${tab === t.id ? 'var(--sage)' : 'transparent'}` }}>
            {t.label}{t.id === 'notes' ? ` · ${facts.length}` : ''}
          </button>
        ))}
      </nav>

      {tab === 'conversation' && (analysis ? (
        <Section title="What IRIS may bring up"
          hint="These decide which observations reach a conversation at all. They are not about tone: a finding held back here is one IRIS does not consider well enough evidenced to raise.">
          <div className="col" style={{ gap: 8 }}>
            <span className="kicker" id="min-confidence-label">minimum confidence</span>
            <div className="row" role="group" aria-labelledby="min-confidence-label" style={{ gap: 6, maxWidth: 420 }}>
              {(['low', 'medium', 'high'] as const).map((level) => (
                <button key={level} className="btn ghost" aria-pressed={analysis.minConfidence === level}
                  onClick={() => setGate({ minConfidence: level })}
                  style={{
                    flex: 1, fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase',
                    padding: '7px 0', borderRadius: 6,
                    border: `1px solid ${analysis.minConfidence === level ? 'var(--sage)' : 'var(--line-soft)'}`,
                    background: analysis.minConfidence === level ? 'rgba(169,200,163,0.10)' : 'transparent',
                    color: analysis.minConfidence === level ? 'var(--sage)' : 'var(--ink-3)',
                  }}>
                  {level}
                </button>
              ))}
            </div>
          </div>

          <div className="col" style={{ gap: 8, maxWidth: 420 }}>
            <label className="kicker" htmlFor="max-items">most observations at once · {maxItems ?? analysis.maxItems}</label>
            {/* Local while dragging; saved once when released. It PATCHed
                on every tick, and each save changes what chat is told. */}
            <input id="max-items" type="range" min={1} max={10} value={maxItems ?? analysis.maxItems}
              onChange={(e) => setMaxItems(Number(e.target.value))}
              onPointerUp={commitMaxItems} onKeyUp={commitMaxItems} onBlur={commitMaxItems}
              style={{ width: '100%', accentColor: 'var(--sage)' }} />
          </div>

          <div className="col" style={{ gap: 8 }}>
            <span className="kicker">what it looks for</span>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '4px 20px' }}>
              {analysis.availableEngines.map((engine) => {
                const on = (analysis.enabledEngines ?? analysis.availableEngines).includes(engine);
                return (
                  <label key={engine} className="row" style={{ gap: 9, alignItems: 'center', cursor: 'pointer', padding: '4px 0' }}>
                    <input type="checkbox" checked={on} onChange={() => toggleEngine(engine)} style={{ accentColor: 'var(--sage)' }} />
                    <span style={{ fontSize: 13, color: on ? 'var(--ink)' : 'var(--ink-4)' }}>{ENGINE_LABELS[engine] ?? engine}</span>
                  </label>
                );
              })}
            </div>
          </div>

          <button className="btn ghost" onClick={async () => { await resetAnalysisPreferences(); afterGateChange(); }}
            style={{ alignSelf: 'flex-start', fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em',
                     textTransform: 'uppercase', color: 'var(--ink-3)' }}>
            restore defaults
          </button>
        </Section>
      ) : <LoadingState label="Loading…" />)}

      {tab === 'phone' && (
        <Section title="Phone"
          hint="The IRIS phone app sends permitted readings here automatically. They wait in Sensors for review; nothing becomes evidence until you link it.">
          <div role="status" className="row" style={{ gap: 10, alignItems: 'center' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: phoneStatus.tone }} />
            <span style={{ fontSize: 15, color: 'var(--ink)' }}>{phoneStatus.text}</span>
          </div>

          {(mobileError || connectionError) && <div role="alert" style={{ color: 'var(--rose)', fontSize: 12.5 }}>
            {mobileError || (connectionError instanceof Error ? connectionError.message : String(connectionError))}
          </div>}

          {mobile && (
            <div className="col" style={{ gap: 8 }}>
              {mobile.lan_url && <Fact label="laptop address"><code style={{ userSelect: 'all' }}>{mobile.lan_url}</code></Fact>}
              {mobile.paired && <Fact label="last contact">{when(mobile.last_seen_at)}</Fact>}
              {mobile.paired && <Fact label="last delivery">{when(mobile.last_intake_at)}</Fact>}
              {mobile.pending_batches > 0 && (
                <Fact label="waiting"><Link to="/sensors">{mobile.pending_batches} sensor batches to review</Link></Fact>
              )}
            </div>
          )}

          {mobile?.listener === 'failed' && (
            <p style={{ ...small, color: 'var(--amber)' }}>
              The phone listener could not start: {mobile.listener_error}. Check that LAN_BIND_HOST in .env is this
              laptop&apos;s home Wi-Fi or Tailscale address, then restart scripts/serve_iris.py.
            </p>
          )}
          {mobile?.listener === 'not_started' && (
            <p style={{ ...small, color: 'var(--amber)' }}>
              LAN_BIND_HOST is set, but IRIS was started without the phone listener. Start it with <code>uv run python scripts/serve_iris.py</code>.
            </p>
          )}
          {mobile?.listener === 'not_configured' && (
            <p style={{ ...small, color: 'var(--amber)' }}>
              No phone listener is configured. Set LAN_BIND_HOST to this laptop&apos;s home Wi-Fi or Tailscale address,
              then start IRIS with <code>uv run python scripts/serve_iris.py</code>.
            </p>
          )}
          {mobile?.paired && !mobile.last_seen_at && (
            <p style={small}>No phone request has reached IRIS since pairing. Check that the phone can reach the laptop
              address above, and that the laptop firewall allows TCP 8765.</p>
          )}
          {mobile?.last_rejection && (
            <p style={{ ...small, color: 'var(--amber)' }}>
              Last refused phone request: {mobile.last_rejection.status} {mobile.last_rejection.detail} at {when(mobile.last_rejection.at)}
            </p>
          )}

          {mobile?.listener === 'listening' && mobile.lan_url && mobile.public_key_sha256 && (
            <>
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                {mobile.paired && !newToken && (
                  <button className="btn" type="button" onClick={() => setShowAddress(v => !v)}>
                    {showAddress ? 'Hide address QR' : 'Show address QR'}
                  </button>
                )}
                <button className="btn" type="button" disabled={mobileBusy} onClick={generatePairing}>
                  {mobileBusy ? 'Saving…' : mobile.paired ? 'Pair a new phone' : 'Pair a phone'}
                </button>
                {mobile.paired && (
                  <button className="btn ghost" type="button" disabled={mobileBusy} onClick={revokePairing}
                    style={{ color: 'var(--rose)' }}>Disconnect phone</button>
                )}
              </div>
              {newToken && (
                <div role="status" className="col" style={{ gap: 8, fontSize: 12.5, color: 'var(--ink-2)' }}>
                  <QrCode value={phonePairingCode(mobile.lan_url, mobile.public_key_sha256, newToken)} label="IRIS pairing QR code" />
                  <span>In the IRIS phone app tap Scan pairing QR. Shown only until you leave this page.</span>
                  <details><summary style={{ cursor: 'pointer', color: 'var(--ink-3)' }}>Pairing token, to type in by hand</summary>
                    <code style={{ display: 'block', userSelect: 'all', wordBreak: 'break-all', marginTop: 6 }}>{newToken}</code>
                  </details>
                </div>
              )}
              {showAddress && mobile.paired && !newToken && (
                <div className="col" style={{ gap: 8, fontSize: 12.5, color: 'var(--ink-2)' }}>
                  <QrCode value={phonePairingCode(mobile.lan_url, mobile.public_key_sha256)} label="IRIS address QR code" />
                  <span>If this laptop&apos;s address changed, scan this from the phone; the pairing is kept.</span>
                </div>
              )}
              <details style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
                <summary style={{ cursor: 'pointer' }}>Technical details</summary>
                <div className="col" style={{ gap: 6, marginTop: 8 }}>
                  <Fact label="server key sha-256">
                    <code style={{ userSelect: 'all', wordBreak: 'break-all' }}>{mobile.public_key_sha256}</code>
                  </Fact>
                </div>
              </details>
            </>
          )}
        </Section>
      )}

      {tab === 'notes' && (
        <Section title="What IRIS knows about you"
          hint="Stable notes inferred from your own words. Remove any of them with × and it is gone; a confirmed pattern asks first.">
          {facts.length === 0 ? <p style={small}>Nothing yet.</p> : (
            <div className="col">
              {facts.map((k, i) => (
                <div key={k.id} style={{ display: 'grid', gridTemplateColumns: '1fr 90px 50px 28px', gap: 12, padding: '12px 0',
                                         alignItems: 'baseline', borderTop: i === 0 ? 'none' : '1px solid var(--line-soft)' }}>
                  <span className="serif" style={{ fontSize: 17, lineHeight: 1.4, color: 'var(--ink)', fontStyle: 'italic' }}>&ldquo;{k.fact}&rdquo;</span>
                  <span className="tag" style={{ justifySelf: 'start', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)' }}>{k.source}</span>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-4)', textAlign: 'right' }}>{k.ageDays}d</span>
                  {k.editable ? (
                    <button className="btn ghost" style={{ fontSize: 13, color: 'var(--rose)', padding: 0 }}
                      aria-label={k.source === 'confirmed' ? 'stop counting' : 'forget'}
                      title={k.source === 'confirmed' ? 'Stop counting this confirmed pattern' : 'Forget this pattern; it can be found again'}
                      onClick={() => forget(k.id, k.source)}>×</button>
                  ) : <span />}
                </div>
              ))}
            </div>
          )}
        </Section>
      )}

      {tab === 'data' && (
        <Section title="Your data">
          <div className="col" style={{ gap: 10 }}>
            <Fact label="stored">On this laptop, in your own PostgreSQL. Nothing is kept anywhere else.</Fact>
            <Fact label="sent to OpenAI">What you write, to be turned into embeddings and replies. Reads over your writing, such as Read my reflections, run only when you start them.</Fact>
            <Fact label="reachable from">This laptop, your paired phone, and your own devices signed in to your Tailscale account.</Fact>
            <Fact label="removable">Every note IRIS keeps about you is listed under Notes and can be removed there.</Fact>
          </div>
        </Section>
      )}
    </div>
  );
}

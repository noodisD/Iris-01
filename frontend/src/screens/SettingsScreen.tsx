import React from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useKnowledge, useAnalysisPreferences } from '@/hooks/useData';
import { forgetFact, updateAnalysisPreferences, resetAnalysisPreferences, getMobileConnection, pairMobile, unpairMobile, phonePairingCode } from '@/api/settings';
import { LoadingState, ErrorState } from '@/components/states';
import { QrCode } from '@/components/QrCode';
import { qk } from '@/lib/queryClient';
import { Button, ChoiceGroup, Page, Section, Tabs, TabPanel } from '@/ui';
import styles from './SettingsScreen.module.css';

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
type TabId = typeof TABS[number]['id'];

/** A labelled line in a list of facts about a connection. */
function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.fact}>
      <dt>{label}</dt>
      <dd>{children}</dd>
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
    ? { tone: 'unknown', text: connectionError ? 'Could not check the phone connection' : 'Checking the phone connection…' }
    : mobile.listener !== 'listening'
      ? { tone: 'warn', text: 'The phone listener is not running' }
      : mobile.paired
        ? { tone: mobile.last_seen_at ? 'ok' : 'unknown', text: mobile.last_seen_at ? 'Phone paired and in touch' : 'Phone paired, not heard from yet' }
        : { tone: 'unknown', text: 'No phone paired' };

  return (
    <Page title="Settings">
      <Tabs<TabId> label="Settings" value={tab} onChange={next => setParams({ tab: next })}
        tabs={TABS.map(t => ({ value: t.id, label: t.id === 'notes' ? `${t.label} (${facts.length})` : t.label }))}>
        <TabPanel value="conversation">
          {analysis ? (
            <Section title="What IRIS may bring up"
              description="These decide which observations reach a conversation at all. They are not about tone: a finding held back here is one IRIS does not consider well enough evidenced to raise.">
              <div className={styles.control}>
                <span className={styles.label}>Minimum confidence</span>
                <ChoiceGroup label="Minimum confidence" value={analysis.minConfidence}
                  options={[{ value: 'low', label: 'Low' }, { value: 'medium', label: 'Medium' }, { value: 'high', label: 'High' }]}
                  onChange={level => { if (level) void setGate({ minConfidence: level }); }} />
              </div>

              <div className={styles.control}>
                <label className={styles.label} htmlFor="max-items">
                  Most observations at once: <span className={styles.value}>{maxItems ?? analysis.maxItems}</span>
                </label>
                {/* Local while dragging; saved once when released. It PATCHed
                    on every tick, and each save changes what chat is told. */}
                <input id="max-items" type="range" min={1} max={10} value={maxItems ?? analysis.maxItems}
                  onChange={(e) => setMaxItems(Number(e.target.value))}
                  onPointerUp={commitMaxItems} onKeyUp={commitMaxItems} onBlur={commitMaxItems}
                  className={styles.range} />
              </div>

              <fieldset className={styles.engines}>
                <legend className={styles.label}>What it looks for</legend>
                {analysis.availableEngines.map((engine) => {
                  const on = (analysis.enabledEngines ?? analysis.availableEngines).includes(engine);
                  return (
                    <label key={engine} className={styles.check}>
                      <input type="checkbox" checked={on} onChange={() => toggleEngine(engine)} />
                      <span>{ENGINE_LABELS[engine] ?? engine}</span>
                    </label>
                  );
                })}
              </fieldset>

              <div>
                <Button variant="quiet" size="sm" onClick={async () => { await resetAnalysisPreferences(); afterGateChange(); }}>
                  Restore defaults
                </Button>
              </div>
            </Section>
          ) : <LoadingState label="Loading…" />}
        </TabPanel>

        <TabPanel value="phone">
          <Section title="Phone"
            description="The IRIS phone app sends permitted readings here automatically. They wait in Sensors for review; nothing becomes evidence until you link it.">
            <p role="status" className={styles.status}>
              <span className={`${styles.light} ${styles[phoneStatus.tone]}`} aria-hidden="true" />
              {phoneStatus.text}
            </p>

            {(mobileError || connectionError) && <p role="alert" className={styles.error}>
              {mobileError || (connectionError instanceof Error ? connectionError.message : String(connectionError))}
            </p>}

            {mobile && (
              <dl className={styles.facts}>
                {mobile.lan_url && <Fact label="Laptop address"><code className={styles.code}>{mobile.lan_url}</code></Fact>}
                {mobile.paired && <Fact label="Last contact">{when(mobile.last_seen_at)}</Fact>}
                {mobile.paired && <Fact label="Last delivery">{when(mobile.last_intake_at)}</Fact>}
                {mobile.pending_batches > 0 && (
                  <Fact label="Waiting"><Link to="/sensors?view=review">{mobile.pending_batches} sensor {mobile.pending_batches === 1 ? 'batch' : 'batches'} to review</Link></Fact>
                )}
              </dl>
            )}

            {mobile?.listener === 'failed' && (
              <p className={styles.warn}>
                The phone listener could not start: {mobile.listener_error}. Check that LAN_BIND_HOST in .env is this
                laptop&apos;s home Wi-Fi or Tailscale address, then restart scripts/serve_iris.py.
              </p>
            )}
            {mobile?.listener === 'not_started' && (
              <p className={styles.warn}>
                LAN_BIND_HOST is set, but IRIS was started without the phone listener. Start it with <code>uv run python scripts/serve_iris.py</code>.
              </p>
            )}
            {mobile?.listener === 'not_configured' && (
              <p className={styles.warn}>
                No phone listener is configured. Set LAN_BIND_HOST to this laptop&apos;s home Wi-Fi or Tailscale address,
                then start IRIS with <code>uv run python scripts/serve_iris.py</code>.
              </p>
            )}
            {mobile?.paired && !mobile.last_seen_at && (
              <p className={styles.muted}>No phone request has reached IRIS since pairing. Check that the phone can reach the laptop
                address above, and that the laptop firewall allows TCP 8765.</p>
            )}
            {mobile?.last_rejection && (
              <p className={styles.warn}>
                Last refused phone request: {mobile.last_rejection.status} {mobile.last_rejection.detail} at {when(mobile.last_rejection.at)}
              </p>
            )}

            {mobile?.listener === 'listening' && mobile.lan_url && mobile.public_key_sha256 && (
              <>
                <div className={styles.actions}>
                  <Button variant={mobile.paired ? 'secondary' : 'primary'} disabled={mobileBusy} onClick={generatePairing}>
                    {mobileBusy ? 'Saving…' : mobile.paired ? 'Pair a new phone' : 'Pair a phone'}
                  </Button>
                  {mobile.paired && !newToken && (
                    <Button onClick={() => setShowAddress(v => !v)}>{showAddress ? 'Hide address QR' : 'Show address QR'}</Button>
                  )}
                  {mobile.paired && (
                    <Button variant="danger" disabled={mobileBusy} onClick={revokePairing}>Disconnect phone</Button>
                  )}
                </div>
                {newToken && (
                  <div role="status" className={styles.qr}>
                    <QrCode value={phonePairingCode(mobile.lan_url, mobile.public_key_sha256, newToken)} label="IRIS pairing QR code" />
                    <p className={styles.muted}>In the IRIS phone app tap Scan pairing QR. Shown only until you leave this page.</p>
                    <details className={styles.details}><summary>Pairing token, to type in by hand</summary>
                      <code className={styles.code}>{newToken}</code>
                    </details>
                  </div>
                )}
                {showAddress && mobile.paired && !newToken && (
                  <div className={styles.qr}>
                    <QrCode value={phonePairingCode(mobile.lan_url, mobile.public_key_sha256)} label="IRIS address QR code" />
                    <p className={styles.muted}>If this laptop&apos;s address changed, scan this from the phone; the pairing is kept.</p>
                  </div>
                )}
                <details className={styles.details}>
                  <summary>Technical details</summary>
                  <dl className={styles.facts}>
                    <Fact label="Server key SHA-256"><code className={styles.code}>{mobile.public_key_sha256}</code></Fact>
                  </dl>
                </details>
              </>
            )}
          </Section>
        </TabPanel>

        <TabPanel value="notes">
          <Section title="What IRIS knows about you"
            description="Stable notes inferred from your own words. Remove any of them and it is gone; a confirmed pattern asks first.">
            {facts.length === 0 ? <p className={styles.muted}>Nothing yet.</p> : (
              <ul className={styles.notes}>
                {facts.map(k => (
                  <li key={k.id} className={styles.note}>
                    <p className={styles.noteText}>{k.fact}</p>
                    <span className={styles.noteMeta}>{k.source === 'confirmed' ? 'Confirmed by you' : k.source}, {k.ageDays} days old</span>
                    {k.editable && (
                      <Button variant="quiet" size="sm" className={styles.remove}
                        aria-label={k.source === 'confirmed' ? 'stop counting' : 'forget'}
                        title={k.source === 'confirmed' ? 'Stop counting this confirmed pattern' : 'Forget this pattern; it can be found again'}
                        onClick={() => forget(k.id, k.source)}>
                        {k.source === 'confirmed' ? 'Stop counting' : 'Forget'}
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </TabPanel>

        <TabPanel value="data">
          <Section title="Your data">
            <dl className={styles.facts}>
              <Fact label="Stored">On this laptop, in your own PostgreSQL. Nothing is kept anywhere else.</Fact>
              <Fact label="Sent to OpenAI">What you write, to be turned into embeddings and replies. Reads over your writing, such as Read my reflections, run only when you start them. When you talk with IRIS, your speech is sent to be transcribed and IRIS's replies to be spoken; the audio is not kept.</Fact>
              <Fact label="Reachable from">This laptop, your paired phone, and your own devices signed in to your Tailscale account.</Fact>
              <Fact label="Removable">Every note IRIS keeps about you is listed under Notes and can be removed there.</Fact>
            </dl>
          </Section>
        </TabPanel>
      </Tabs>
    </Page>
  );
}

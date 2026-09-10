import React from 'react';

/**
 * Recording a voice journal in the browser.
 *
 * Three things here are less obvious than they look, and each ships as a bug if
 * skipped: every track must be stopped on unmount *and* on discard or the
 * browser's recording indicator stays lit after the user thinks they stopped;
 * MediaRecorder and navigator.mediaDevices have to be feature-detected, because
 * getUserMedia is unavailable outside a secure context and the whole feature
 * would otherwise throw rather than simply not offer itself; and "permission
 * denied" and "no microphone found" need different words, because they need
 * different actions from the person reading them.
 */

const MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
  'audio/ogg;codecs=opus',
];

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined;
  return MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported?.(t));
}

export function isRecordingSupported(): boolean {
  return (
    typeof MediaRecorder !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia
  );
}

type Phase = 'idle' | 'requesting' | 'recording' | 'review' | 'saving';

export function AudioRecorder({
  onSave, disabled,
}: {
  onSave: (blob: Blob, filename: string, recordedAt: string) => Promise<void>;
  disabled?: boolean;
}) {
  const [phase, setPhase] = React.useState<Phase>('idle');
  const [error, setError] = React.useState<string>();
  const [seconds, setSeconds] = React.useState(0);
  const [level, setLevel] = React.useState(0);
  const [clip, setClip] = React.useState<{ blob: Blob; url: string; startedAt: string }>();

  const stream = React.useRef<MediaStream>();
  const recorder = React.useRef<MediaRecorder>();
  const chunks = React.useRef<Blob[]>([]);
  const audioCtx = React.useRef<AudioContext>();
  const raf = React.useRef<number>();
  const startedAt = React.useRef<string>('');

  const releaseMic = React.useCallback(() => {
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = undefined;
    if (raf.current) cancelAnimationFrame(raf.current);
    audioCtx.current?.close().catch(() => {});
    audioCtx.current = undefined;
    setLevel(0);
  }, []);

  // The microphone must not outlive the component, however it unmounts.
  React.useEffect(() => releaseMic, [releaseMic]);

  React.useEffect(() => {
    if (phase !== 'recording') return;
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [phase]);

  const meter = (source: MediaStream) => {
    try {
      const ctx = new AudioContext();
      audioCtx.current = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      ctx.createMediaStreamSource(source).connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        const peak = data.reduce((m, v) => Math.max(m, Math.abs(v - 128)), 0);
        setLevel(Math.min(1, peak / 96));
        raf.current = requestAnimationFrame(tick);
      };
      tick();
    } catch {
      // A level meter is decoration; losing it must not cost the recording.
    }
  };

  const start = async () => {
    setError(undefined);
    setPhase('requesting');
    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = mic;
      const mimeType = pickMimeType();
      const rec = new MediaRecorder(mic, mimeType ? { mimeType } : undefined);
      chunks.current = [];
      rec.ondataavailable = (e) => { if (e.data.size) chunks.current.push(e.data); };
      rec.onstop = () => {
        const blob = new Blob(chunks.current, { type: rec.mimeType || 'audio/webm' });
        releaseMic();
        setClip({ blob, url: URL.createObjectURL(blob), startedAt: startedAt.current });
        setPhase('review');
      };
      startedAt.current = new Date().toISOString();
      setSeconds(0);
      rec.start();
      recorder.current = rec;
      meter(mic);
      setPhase('recording');
    } catch (e) {
      releaseMic();
      setPhase('idle');
      const name = (e as DOMException)?.name;
      // Different causes, different remedies — so different words.
      setError(
        name === 'NotAllowedError'
          ? 'IRIS needs permission to use your microphone. Allow it in your browser and try again.'
          : name === 'NotFoundError'
            ? 'No microphone was found.'
            : 'The microphone could not be opened.',
      );
    }
  };

  const discard = () => {
    if (clip) URL.revokeObjectURL(clip.url);
    setClip(undefined);
    releaseMic();
    setPhase('idle');
  };

  const save = async () => {
    if (!clip) return;
    setPhase('saving');
    const extension = clip.blob.type.includes('mp4') ? 'm4a'
      : clip.blob.type.includes('ogg') ? 'ogg' : 'webm';
    try {
      await onSave(clip.blob, `recording-${clip.startedAt.slice(0, 19)}.${extension}`, clip.startedAt);
      discard();
    } catch (e) {
      setPhase('review');
      setError(e instanceof Error ? e.message : 'The recording could not be saved.');
    }
  };

  if (!isRecordingSupported()) return null;

  const clock = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;

  return (
    <div className="col" style={{ gap: 10 }}>
      {error && (
        <span style={{ fontSize: 11.5, color: 'var(--rose)', fontStyle: 'italic' }}>{error}</span>
      )}

      {phase === 'idle' && (
        <button className="btn" onClick={start} disabled={disabled}>Record an entry</button>
      )}

      {phase === 'requesting' && (
        <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Waiting for the microphone…</span>
      )}

      {phase === 'recording' && (
        <div className="row" style={{ gap: 12, alignItems: 'center' }}>
          <span className="dot rose" style={{ animation: 'breathe 1.6s ease-in-out infinite' }} />
          <span style={{ fontFamily: 'var(--mono)', fontSize: 13, color: 'var(--ink)' }}>{clock}</span>
          <div style={{ flex: 1, height: 2, background: 'var(--line-soft)', borderRadius: 1 }}>
            <div style={{
              width: `${Math.round(level * 100)}%`, height: '100%',
              background: 'var(--sage)', borderRadius: 1, transition: 'width 0.08s',
            }} />
          </div>
          <button className="btn" onClick={() => recorder.current?.stop()}>Stop</button>
        </div>
      )}

      {(phase === 'review' || phase === 'saving') && clip && (
        <div className="col" style={{ gap: 8 }}>
          <audio src={clip.url} controls style={{ width: '100%' }} />
          <div className="row" style={{ gap: 8 }}>
            <button className="btn primary" onClick={save} disabled={phase === 'saving'}>
              {phase === 'saving' ? 'saving…' : 'Save and transcribe'}
            </button>
            <button className="btn ghost" onClick={discard} disabled={phase === 'saving'}
                    style={{ color: 'var(--ink-4)' }}>
              discard
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

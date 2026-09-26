import React from 'react';
import { Button } from '@/ui';
import styles from './AudioRecorder.module.css';

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
    <div className={styles.recorder}>
      {error && <p role="alert" className={styles.error}>{error}</p>}

      {phase === 'idle' && (
        <Button onClick={start} disabled={disabled} className={styles.start}>Record an entry</Button>
      )}

      {phase === 'requesting' && <p className={styles.muted}>Waiting for the microphone…</p>}

      {phase === 'recording' && (
        <div className={styles.row}>
          <span className={styles.live} aria-hidden="true" />
          <span className={styles.clock} aria-label="Recording time">{clock}</span>
          <meter className={styles.level} min={0} max={1} value={level} aria-label="Input level" />
          <Button onClick={() => recorder.current?.stop()}>Stop</Button>
        </div>
      )}

      {(phase === 'review' || phase === 'saving') && clip && (
        <div className={styles.review}>
          <audio src={clip.url} controls className={styles.audio} />
          <div className={styles.row}>
            <Button variant="primary" onClick={save} disabled={phase === 'saving'}>
              {phase === 'saving' ? 'Saving…' : 'Save and transcribe'}
            </Button>
            <Button variant="quiet" onClick={discard} disabled={phase === 'saving'}>Discard</Button>
          </div>
        </div>
      )}
    </div>
  );
}

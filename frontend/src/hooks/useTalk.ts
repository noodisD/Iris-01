import React from 'react';
import * as voiceApi from '@/api/voice';
import { MIN_TURN_SAMPLES, SentenceSplitter, TALK_OFF, encodeWav, talkReducer, type TalkState } from '@/lib/talk';

/** Sends one heard turn through chat; calls back with each fragment of the reply. */
export type SendSpoken = (text: string, onFragment: (fragment: string) => void) => Promise<unknown>;

interface Queued { audio: Promise<AudioBuffer | null> }

/**
 * IRIS's voice: sentences are fetched as they arrive and played in order, the
 * first while the rest of the reply is still being written. `stop` silences it
 * at once, for when the owner talks over IRIS.
 */
class Speaker {
  private queue: Queued[] = [];
  private playing = false;
  private finished = false;
  private started = false;
  private source: AudioBufferSourceNode | null = null;
  private controller = new AbortController();
  private generation = 0;
  readonly analyser: AnalyserNode;
  private readonly samples: Uint8Array<ArrayBuffer>;

  constructor(
    private readonly ctx: AudioContext,
    private readonly on: { start: () => void; done: () => void; trouble: (message: string) => void },
  ) {
    this.analyser = ctx.createAnalyser();
    this.analyser.fftSize = 512;
    this.analyser.connect(ctx.destination);
    this.samples = new Uint8Array(this.analyser.fftSize);
  }

  /** A new reply begins. */
  reset(): void {
    this.stop();
    this.finished = false;
    this.started = false;
  }

  enqueue(sentence: string): void {
    const signal = this.controller.signal;
    const audio = voiceApi.speech(sentence, signal)
      .then(bytes => this.ctx.decodeAudioData(bytes))
      .catch((err: unknown) => {
        if (!signal.aborted) this.on.trouble(err instanceof Error ? err.message : 'IRIS could not speak that.');
        return null;
      });
    this.queue.push({ audio });
    if (!this.playing) void this.playNext();
  }

  /** The reply is complete: once the queue empties, IRIS is done speaking. */
  finish(): void {
    this.finished = true;
    if (!this.playing && this.queue.length === 0) this.on.done();
  }

  stop(): void {
    this.generation += 1;
    this.controller.abort();
    this.controller = new AbortController();
    this.queue = [];
    this.playing = false;
    try { this.source?.stop(); } catch { /* already stopped */ }
    this.source = null;
  }

  /** How loud IRIS is right now, 0 to 1, for the lens. */
  level(): number {
    this.analyser.getByteTimeDomainData(this.samples);
    let sum = 0;
    for (const v of this.samples) sum += ((v - 128) / 128) ** 2;
    return Math.min(1, Math.sqrt(sum / this.samples.length) * 4);
  }

  private async playNext(): Promise<void> {
    const generation = this.generation;
    const next = this.queue.shift();
    if (!next) {
      this.playing = false;
      if (this.finished) this.on.done();
      return;
    }
    this.playing = true;
    const buffer = await next.audio;
    if (generation !== this.generation) return;
    if (!buffer) { void this.playNext(); return; }
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.analyser);
    source.onended = () => { if (generation === this.generation) void this.playNext(); };
    this.source = source;
    if (!this.started) { this.started = true; this.on.start(); }
    source.start();
  }
}

function microphoneProblem(err: unknown): string {
  const name = err instanceof DOMException ? err.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'IRIS needs your microphone. Allow it for this site in the browser, then start again.';
  }
  if (name === 'NotFoundError') return 'No microphone was found. Connect one, then start again.';
  return `Talking could not start: ${err instanceof Error ? err.message : String(err)}`;
}

/**
 * A spoken conversation (ADR-0025): listen until the owner stops, transcribe,
 * send through chat, speak the reply a sentence at a time, listen again.
 * `levelRef` is the element whose `--level` follows the voice being heard or
 * spoken, for the lens.
 */
export function useTalk(send: SendSpoken) {
  const [state, dispatch] = React.useReducer(talkReducer, TALK_OFF);
  const phase = React.useRef<TalkState['phase']>('off');
  phase.current = state.phase;
  const levelRef = React.useRef<HTMLDivElement>(null);
  const vad = React.useRef<{ start: () => void | Promise<void>; pause: () => void | Promise<void>; destroy: () => void | Promise<void> } | null>(null);
  const speaker = React.useRef<Speaker | null>(null);
  const ctx = React.useRef<AudioContext | null>(null);
  const turns = React.useRef({ next: 0, active: -1, running: Promise.resolve() as Promise<unknown> });
  const sendRef = React.useRef(send);
  sendRef.current = send;

  const setLevel = (value: number) => levelRef.current?.style.setProperty('--level', value.toFixed(3));

  const silence = React.useCallback(() => {
    turns.current.active = -1;
    speaker.current?.stop();
  }, []);

  const takeTurn = React.useCallback(async (audio: Float32Array) => {
    if (phase.current !== 'hearing') return;
    dispatch({ type: 'speechEnd' });
    setLevel(0);
    if (audio.length < MIN_TURN_SAMPLES) { dispatch({ type: 'heardNothing' }); return; }
    let text: string;
    try {
      text = (await voiceApi.transcribe(encodeWav(audio))).trim();
    } catch (err) {
      dispatch({ type: 'trouble', message: err instanceof Error ? err.message : 'IRIS could not hear that.' });
      return;
    }
    if (!text) { dispatch({ type: 'heardNothing' }); return; }
    // A reply the owner talked over may still be arriving; turns never overlap.
    await turns.current.running.catch(() => undefined);
    const id = ++turns.current.next;
    turns.current.active = id;
    const splitter = new SentenceSplitter();
    const voice = speaker.current!;
    voice.reset();
    const speak = (sentences: string[]) => {
      if (turns.current.active === id) sentences.forEach(s => voice.enqueue(s));
    };
    const running = sendRef.current(text, fragment => speak(splitter.push(fragment)));
    turns.current.running = running;
    try {
      await running;
      speak(splitter.flush());
      if (turns.current.active === id) voice.finish();
    } catch (err) {
      if (turns.current.active === id) {
        voice.stop();
        dispatch({ type: 'trouble', message: err instanceof Error ? err.message : 'IRIS could not reply.' });
      }
    }
  }, []);

  const end = React.useCallback(() => {
    silence();
    void vad.current?.destroy();
    vad.current = null;
    void ctx.current?.close();
    ctx.current = null;
    speaker.current = null;
    dispatch({ type: 'end' });
  }, [silence]);

  const start = React.useCallback(async () => {
    dispatch({ type: 'start' });
    try {
      const audio = new AudioContext();
      ctx.current = audio;
      speaker.current = new Speaker(audio, {
        start: () => dispatch({ type: 'replyStarted' }),
        done: () => dispatch({ type: 'spoken' }),
        trouble: message => dispatch({ type: 'trouble', message }),
      });
      // Loaded only now: the model and runtime are large, and most visits to
      // Chat never talk.
      const { MicVAD } = await import('@ricky0123/vad-web');
      vad.current = await MicVAD.new({
        model: 'v5',
        baseAssetPath: '/assets/vad/',
        onnxWASMBasePath: '/assets/vad/',
        positiveSpeechThreshold: 0.5,
        negativeSpeechThreshold: 0.35,
        // How long a pause ends the turn: long enough to think mid-sentence.
        redemptionMs: 900,
        minSpeechMs: 400,
        preSpeechPadMs: 300,
        getStream: () => navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        }),
        // "Real" start, after enough speech to be sure: a cough or IRIS's own
        // voice leaking past echo cancellation should not stop IRIS.
        onSpeechRealStart: () => {
          if (phase.current === 'speaking') silence();
          dispatch({ type: 'speechStart' });
        },
        onVADMisfire: () => dispatch({ type: 'misfire' }),
        onSpeechEnd: (samples: Float32Array) => { void takeTurn(samples); },
        onFrameProcessed: (p: { isSpeech: number }) => {
          if (phase.current === 'hearing') setLevel(p.isSpeech);
        },
      });
      await vad.current.start();
      dispatch({ type: 'ready' });
    } catch (err) {
      silence();
      void vad.current?.destroy();
      vad.current = null;
      void ctx.current?.close();
      ctx.current = null;
      dispatch({ type: 'fail', message: microphoneProblem(err) });
    }
  }, [silence, takeTurn]);

  const pause = React.useCallback(() => {
    if (phase.current === 'speaking') silence();
    void vad.current?.pause();
    dispatch({ type: 'pause' });
  }, [silence]);

  const resume = React.useCallback(() => {
    void vad.current?.start();
    dispatch({ type: 'resume' });
  }, []);

  const stopSpeaking = React.useCallback(() => {
    silence();
    dispatch({ type: 'stopSpeaking' });
  }, [silence]);

  // The lens follows IRIS's voice while it speaks.
  React.useEffect(() => {
    if (state.phase !== 'speaking') return;
    let frame = 0;
    const tick = () => {
      setLevel(speaker.current?.level() ?? 0);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(frame); setLevel(0); };
  }, [state.phase]);

  // Leaving Chat ends the conversation and releases the microphone.
  React.useEffect(() => () => end(), [end]);

  return { state, levelRef, start, end, pause, resume, stopSpeaking };
}

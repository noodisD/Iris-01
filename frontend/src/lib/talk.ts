/**
 * Talk mode's logic, kept free of the browser so it can be tested (ADR-0025):
 * the turn-taking state machine, the splitting of a streamed reply into
 * sentences IRIS can speak one at a time, and the WAV encoding of what the
 * owner said.
 */

export type TalkPhase =
  | 'off'        // not talking
  | 'starting'   // asking for the microphone, loading voice detection
  | 'listening'  // waiting for the owner to speak
  | 'hearing'    // the owner is speaking
  | 'thinking'   // transcribing, then waiting for IRIS's first sentence
  | 'speaking'   // IRIS is speaking
  | 'paused'     // listening is paused by the owner
  | 'error';     // talking cannot go on; `error` says why

export interface TalkState {
  phase: TalkPhase;
  /** Why talking stopped (phase `error`), or a passing problem with one turn. */
  error: string | null;
}

export type TalkEvent =
  | { type: 'start' }
  | { type: 'ready' }
  | { type: 'speechStart' }
  | { type: 'speechEnd' }
  | { type: 'misfire' }
  | { type: 'heardNothing' }
  | { type: 'replyStarted' }
  | { type: 'spoken' }
  | { type: 'stopSpeaking' }
  | { type: 'pause' }
  | { type: 'resume' }
  | { type: 'trouble'; message: string }
  | { type: 'fail'; message: string }
  | { type: 'end' };

export const TALK_OFF: TalkState = { phase: 'off', error: null };

/**
 * What happens next. Anything not listed for a phase is ignored, which is how
 * the owner's voice is not taken as a new turn while IRIS is still thinking
 * about the last one: turns never overlap.
 */
export function talkReducer(state: TalkState, event: TalkEvent): TalkState {
  if (event.type === 'end') return TALK_OFF;
  if (event.type === 'fail') return { phase: 'error', error: event.message };
  const to = (phase: TalkPhase, error: string | null = null): TalkState => ({ phase, error });
  switch (state.phase) {
    case 'off':
    case 'error':
      return event.type === 'start' ? to('starting') : state;
    case 'starting':
      return event.type === 'ready' ? to('listening') : state;
    case 'listening':
      if (event.type === 'speechStart') return to('hearing');
      if (event.type === 'pause') return to('paused');
      return state;
    case 'hearing':
      if (event.type === 'speechEnd') return to('thinking');
      if (event.type === 'misfire') return to('listening', state.error);
      if (event.type === 'pause') return to('paused');
      return state;
    case 'thinking':
      if (event.type === 'replyStarted') return to('speaking');
      if (event.type === 'heardNothing') return to('listening');
      if (event.type === 'spoken') return to('listening');
      if (event.type === 'trouble') return to('listening', event.message);
      return state;
    case 'speaking':
      // Talking over IRIS stops it and takes the turn.
      if (event.type === 'speechStart') return to('hearing');
      if (event.type === 'spoken' || event.type === 'stopSpeaking') return to('listening');
      if (event.type === 'pause') return to('paused');
      if (event.type === 'trouble') return to('listening', event.message);
      return state;
    case 'paused':
      return event.type === 'resume' ? to('listening') : state;
  }
}

/** Words ending in a full stop that do not end a sentence. */
const ABBREVIATIONS = new Set([
  'e.g', 'i.e', 'etc', 'vs', 'mr', 'mrs', 'ms', 'dr', 'st', 'no', 'approx', 'cf', 'p.s',
]);
/** Short enough to be heard as a whole; longer text is split at a pause. */
const MAX_SPOKEN = 500;

/** What IRIS would read aloud: markdown and link syntax are not words. */
export function speakable(text: string): string {
  return text
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[*_`#>]+/g, '')
    .replace(/^\s*[-•]\s+/gm, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function splitLong(sentence: string): string[] {
  const out: string[] = [];
  let rest = sentence;
  while (rest.length > MAX_SPOKEN) {
    const window = rest.slice(0, MAX_SPOKEN);
    const cut = Math.max(window.lastIndexOf(', '), window.lastIndexOf('; '), window.lastIndexOf(' '));
    const at = cut > 0 ? cut + 1 : MAX_SPOKEN;
    out.push(rest.slice(0, at).trim());
    rest = rest.slice(at).trim();
  }
  if (rest) out.push(rest);
  return out;
}

/**
 * Splits a reply streamed in fragments into sentences as soon as each is
 * complete, so IRIS can start speaking the first while the rest is written.
 */
export class SentenceSplitter {
  private buffer = '';

  push(fragment: string): string[] {
    this.buffer += fragment;
    const out: string[] = [];
    // A sentence ends at . ! ? or … followed by space, or at a line break.
    const end = /([.!?…]+)(["'”’)]*)(\s+)|\n+/g;
    let start = 0;
    let match: RegExpExecArray | null;
    while ((match = end.exec(this.buffer)) !== null) {
      const candidate = this.buffer.slice(start, match.index + (match[1] ? match[1].length + match[2].length : 0));
      if (match[1] === '.' && this.isAbbreviation(candidate)) continue;
      const sentence = speakable(candidate);
      if (sentence) out.push(...splitLong(sentence));
      start = match.index + match[0].length;
    }
    this.buffer = this.buffer.slice(start);
    return out;
  }

  /** Whatever is left once the reply has finished. */
  flush(): string[] {
    const rest = speakable(this.buffer);
    this.buffer = '';
    return rest ? splitLong(rest) : [];
  }

  private isAbbreviation(candidate: string): boolean {
    const word = candidate.slice(0, -1).split(/\s+/).pop()?.toLowerCase() ?? '';
    return ABBREVIATIONS.has(word) || /^[a-z]$/i.test(word);
  }
}

/** 16 kHz mono samples between -1 and 1 as a WAV file, what voice detection hands over. */
export function encodeWav(samples: Float32Array, sampleRate = 16000): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };
  text(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, 'WAVE');
  text(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buffer], { type: 'audio/wav' });
}

/** Under half a second is a cough or a click, not a turn. */
export const MIN_TURN_SAMPLES = 16000 / 2;

/**
 * A spoken conversation, turn by turn, with the microphone's voice detection,
 * the speech service and the audio device replaced by scripts.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const vad = vi.hoisted(() => ({
  options: null as null | Record<string, (...args: never[]) => unknown>,
  paused: 0,
}));
const api = vi.hoisted(() => ({
  heard: 'What should I plant along the north fence?',
  spoken: [] as string[],
  transcribed: 0,
}));

vi.mock('@ricky0123/vad-web', () => ({
  MicVAD: {
    new: async (options: Record<string, (...args: never[]) => unknown>) => {
      vad.options = options;
      return { start: async () => undefined, pause: async () => { vad.paused += 1; }, destroy: async () => undefined };
    },
  },
}));

vi.mock('@/api/voice', () => ({
  transcribe: async () => { api.transcribed += 1; return api.heard; },
  speech: async (text: string) => { api.spoken.push(text); return new ArrayBuffer(8); },
}));

/** Just enough of an AudioContext: each sentence "plays" until ended by hand. */
const playing: { onended: (() => void) | null; stopped: boolean }[] = [];
class FakeAudioContext {
  destination = {};
  createAnalyser() {
    return { fftSize: 0, connect: () => undefined, getByteTimeDomainData: (a: Uint8Array) => a.fill(128) };
  }
  async decodeAudioData() { return {}; }
  createBufferSource() {
    const source = {
      buffer: null as unknown, onended: null as (() => void) | null, stopped: false,
      connect: () => undefined, start: () => { playing.push(source); },
      stop: () => { source.stopped = true; },
    };
    return source;
  }
  async close() { return undefined; }
}
vi.stubGlobal('AudioContext', FakeAudioContext);

import { useTalk, type SendSpoken } from './useTalk';

const speech = (seconds: number) => new Float32Array(16000 * seconds);
const call = async (name: string, ...args: unknown[]) => {
  await act(async () => { await (vad.options![name] as (...a: unknown[]) => unknown)(...args); });
};

/** A chat send that streams the given fragments, then finishes. */
function replying(fragments: string[]): { send: SendSpoken; sent: string[] } {
  const sent: string[] = [];
  const send: SendSpoken = async (text, onFragment) => {
    sent.push(text);
    for (const f of fragments) { await Promise.resolve(); onFragment(f); }
  };
  return { send, sent };
}

async function started(send: SendSpoken) {
  const hook = renderHook(() => useTalk(send));
  await act(async () => { await hook.result.current.start(); });
  expect(hook.result.current.state.phase).toBe('listening');
  return hook;
}

describe('a spoken turn', () => {
  beforeEach(() => {
    vad.options = null; vad.paused = 0;
    api.spoken = []; api.transcribed = 0; api.heard = 'What should I plant along the north fence?';
    playing.length = 0;
  });

  it('is heard, sent through chat as a spoken turn, and answered a sentence at a time', async () => {
    const { send, sent } = replying(['Beans would do well there. ', 'They like sun.']);
    const hook = await started(send);

    await call('onSpeechRealStart');
    expect(hook.result.current.state.phase).toBe('hearing');
    await call('onSpeechEnd', speech(2));

    expect(sent).toEqual(['What should I plant along the north fence?']);
    await waitFor(() => expect(api.spoken).toEqual(['Beans would do well there.', 'They like sun.']));
    await waitFor(() => expect(hook.result.current.state.phase).toBe('speaking'));

    // Each sentence in turn, then IRIS is done and listens again.
    await act(async () => { playing[0].onended?.(); });
    await waitFor(() => expect(playing).toHaveLength(2));
    await act(async () => { playing[1].onended?.(); });
    await waitFor(() => expect(hook.result.current.state.phase).toBe('listening'));
  });

  it('stops speaking when the owner talks over IRIS', async () => {
    const { send } = replying(['One thing. ', 'Another thing. ', 'A third.']);
    const hook = await started(send);
    await call('onSpeechRealStart');
    await call('onSpeechEnd', speech(2));
    await waitFor(() => expect(hook.result.current.state.phase).toBe('speaking'));

    await call('onSpeechRealStart');

    expect(hook.result.current.state.phase).toBe('hearing');
    expect(playing[0].stopped).toBe(true);
    await act(async () => { playing[0].onended?.(); });
    expect(playing).toHaveLength(1);
  });

  it('drops a turn too short to be speech, sending nothing', async () => {
    const { send, sent } = replying(['Hello.']);
    const hook = await started(send);
    await call('onSpeechRealStart');
    await call('onSpeechEnd', speech(0.2));

    expect(hook.result.current.state.phase).toBe('listening');
    expect(api.transcribed).toBe(0);
    expect(sent).toEqual([]);
  });

  it('says so when the reply fails, and listens again', async () => {
    const send: SendSpoken = async () => { throw new Error('IRIS could not reply.'); };
    const hook = await started(send);
    await call('onSpeechRealStart');
    await call('onSpeechEnd', speech(2));

    await waitFor(() => expect(hook.result.current.state).toEqual({ phase: 'listening', error: 'IRIS could not reply.' }));
  });

  it('explains a refused microphone', async () => {
    const { MicVAD } = await import('@ricky0123/vad-web');
    vi.spyOn(MicVAD, 'new').mockRejectedValueOnce(new DOMException('denied', 'NotAllowedError'));
    const hook = renderHook(() => useTalk(replying([]).send));
    await act(async () => { await hook.result.current.start(); });
    expect(hook.result.current.state.phase).toBe('error');
    expect(hook.result.current.state.error).toMatch(/needs your microphone/);
  });
});

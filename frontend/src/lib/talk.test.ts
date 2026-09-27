import { describe, expect, it } from 'vitest';
import { SentenceSplitter, TALK_OFF, encodeWav, speakable, talkReducer, type TalkEvent, type TalkState } from './talk';

const run = (events: TalkEvent[], from: TalkState = TALK_OFF) => events.reduce(talkReducer, from);

describe('taking turns', () => {
  it('listens, hears, thinks, speaks and listens again', () => {
    const phases: string[] = [];
    [{ type: 'start' }, { type: 'ready' }, { type: 'speechStart' }, { type: 'speechEnd' },
      { type: 'replyStarted' }, { type: 'spoken' }].reduce((state, event) => {
      const next = talkReducer(state, event as TalkEvent);
      phases.push(next.phase);
      return next;
    }, TALK_OFF);
    expect(phases).toEqual(['starting', 'listening', 'hearing', 'thinking', 'speaking', 'listening']);
  });

  it('stops speaking when the owner talks over IRIS, and takes their turn', () => {
    const speaking = run([{ type: 'start' }, { type: 'ready' }, { type: 'speechStart' }, { type: 'speechEnd' }, { type: 'replyStarted' }]);
    expect(talkReducer(speaking, { type: 'speechStart' }).phase).toBe('hearing');
  });

  it('does not start a second turn while IRIS is still thinking', () => {
    const thinking = run([{ type: 'start' }, { type: 'ready' }, { type: 'speechStart' }, { type: 'speechEnd' }]);
    expect(talkReducer(thinking, { type: 'speechStart' })).toBe(thinking);
  });

  it('drops a turn that heard nothing, and says when one went wrong', () => {
    const thinking = run([{ type: 'start' }, { type: 'ready' }, { type: 'speechStart' }, { type: 'speechEnd' }]);
    expect(talkReducer(thinking, { type: 'heardNothing' })).toEqual({ phase: 'listening', error: null });
    expect(talkReducer(thinking, { type: 'trouble', message: 'IRIS could not hear that.' }))
      .toEqual({ phase: 'listening', error: 'IRIS could not hear that.' });
  });

  it('pauses, resumes, fails and ends from anywhere', () => {
    const listening = run([{ type: 'start' }, { type: 'ready' }]);
    expect(run([{ type: 'pause' }, { type: 'speechStart' }], listening).phase).toBe('paused');
    expect(run([{ type: 'pause' }, { type: 'resume' }], listening).phase).toBe('listening');
    expect(talkReducer(listening, { type: 'fail', message: 'No microphone.' })).toEqual({ phase: 'error', error: 'No microphone.' });
    expect(talkReducer(listening, { type: 'end' })).toEqual(TALK_OFF);
  });
});

describe('speaking a reply a sentence at a time', () => {
  it('hands over each sentence as soon as it is complete', () => {
    const splitter = new SentenceSplitter();
    expect(splitter.push('Beans would do ')).toEqual([]);
    expect(splitter.push('well there. They like ')).toEqual(['Beans would do well there.']);
    expect(splitter.push('sun! Would you')).toEqual(['They like sun!']);
    expect(splitter.flush()).toEqual(['Would you']);
  });

  it('does not end a sentence at an abbreviation, an initial or a decimal', () => {
    const splitter = new SentenceSplitter();
    const out = splitter.push('Try hardy plants, e.g. kale or chard. Mr. Lee grew 3.5 kg of it. J. R. said so. ');
    expect(out).toEqual(['Try hardy plants, e.g. kale or chard.', 'Mr. Lee grew 3.5 kg of it.', 'J. R. said so.']);
  });

  it('reads no markdown aloud', () => {
    expect(speakable('**Water** the [beds](http://x) at `dusk`.')).toBe('Water the beds at dusk.');
  });

  it('splits a very long sentence at a pause', () => {
    const splitter = new SentenceSplitter();
    const long = `${'word, '.repeat(120)}end.`;
    const parts = [...splitter.push(`${long} `), ...splitter.flush()];
    expect(parts.length).toBeGreaterThan(1);
    expect(parts.every(p => p.length <= 500)).toBe(true);
  });
});

describe('what the owner said, as a file', () => {
  it('is a 16 kHz mono WAV of the right length', async () => {
    const blob = encodeWav(new Float32Array(16000));
    expect(blob.type).toBe('audio/wav');
    expect(blob.size).toBe(44 + 32000);
    const bytes = await new Promise<ArrayBuffer>(resolve => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as ArrayBuffer);
      reader.readAsArrayBuffer(blob);
    });
    const head = new Uint8Array(bytes).slice(0, 4);
    expect(String.fromCharCode(...head)).toBe('RIFF');
  });
});

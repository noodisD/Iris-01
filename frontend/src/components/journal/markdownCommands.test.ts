import { describe, expect, it } from 'vitest';
import { bold, bullet, checklist, commandFor, h1, heading, prefixLines, quote, wrap } from './markdownCommands';

describe('wrap', () => {
  it('wraps a selection and leaves the cursor between markers when nothing is selected', () => {
    expect(wrap('salt', 4, 4, '**')).toEqual({ text: 'salt****', start: 6, end: 6 });
    expect(wrap('salt', 0, 4, '**')).toEqual({ text: '**salt**', start: 2, end: 6 });
  });
});

describe('prefixLines', () => {
  it('prefixes each selected line and toggles the prefix off', () => {
    expect(prefixLines('salt\npepper', 0, 11, '- ')).toEqual({
      text: '- salt\n- pepper',
      start: 0,
      end: 15,
    });
    expect(prefixLines('- salt\n- pepper', 0, 15, '- ').text).toBe('salt\npepper');
  });
});

describe('named commands', () => {
  it('adds a heading, a checklist and a quote', () => {
    expect(heading(2)('soup', 0, 4).text).toBe('## soup');
    expect(checklist('onions', 0, 6).text).toBe('- [ ] onions');
    expect(quote('note', 0, 4).text).toBe('> note');
    expect(bullet('salt', 0, 4).text).toBe('- salt');
    expect(bold('salt', 0, 4).text).toBe('**salt**');
  });
});

describe('commandFor', () => {
  const base = { metaKey: true, ctrlKey: false, altKey: false, shiftKey: false };
  it('maps the editor shortcuts', () => {
    expect(commandFor({ ...base, key: 'b' })).toBe(bold);
    expect(commandFor({ ...base, key: '1', altKey: true })).toBe(h1);
    expect(commandFor({ ...base, key: '8', shiftKey: true })).toBe(bullet);
    expect(commandFor({ ...base, key: '9', shiftKey: true })).toBe(checklist);
    expect(commandFor({ ...base, key: '.', shiftKey: true })).toBe(quote);
    expect(commandFor({ ...base, key: 'b', metaKey: false })).toBeNull();
  });
});

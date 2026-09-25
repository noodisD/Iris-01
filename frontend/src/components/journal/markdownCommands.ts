export interface Span {
  text: string;
  start: number;
  end: number;
}

export type Command = (text: string, start: number, end: number) => Span;

function clamp(text: string, start: number, end: number): [number, number] {
  const from = Math.max(0, Math.min(start, text.length));
  const to = Math.max(0, Math.min(end, text.length));
  return from <= to ? [from, to] : [to, from];
}

export function wrap(text: string, start: number, end: number, marker: string): Span {
  const [from, to] = clamp(text, start, end);
  const selected = text.slice(from, to);
  const next = text.slice(0, from) + marker + selected + marker + text.slice(to);
  const selStart = from + marker.length;
  return { text: next, start: selStart, end: selected ? to + marker.length : selStart };
}

export function prefixLines(text: string, start: number, end: number, prefix: string): Span {
  const [from, to] = clamp(text, start, end);
  const lineStart = text.lastIndexOf('\n', from - 1) + 1;
  const lineBreak = text.indexOf('\n', to);
  const blockEnd = lineBreak === -1 ? text.length : lineBreak;
  const lines = text.slice(lineStart, blockEnd).split('\n');
  const nonempty = lines.filter(line => line.length > 0);
  const remove = nonempty.length > 0 && nonempty.every(line => line.startsWith(prefix));
  const replaced = lines.map(line => {
    if (line.length === 0) return line;
    if (remove) return line.startsWith(prefix) ? line.slice(prefix.length) : line;
    return line.startsWith(prefix) ? line : prefix + line;
  }).join('\n');
  return {
    text: text.slice(0, lineStart) + replaced + text.slice(blockEnd),
    start: lineStart,
    end: lineStart + replaced.length,
  };
}

export const bold: Command = (text, start, end) => wrap(text, start, end, '**');
export const italic: Command = (text, start, end) => wrap(text, start, end, '*');
export const h1: Command = (text, start, end) => prefixLines(text, start, end, '# ');
export const h2: Command = (text, start, end) => prefixLines(text, start, end, '## ');
export const h3: Command = (text, start, end) => prefixLines(text, start, end, '### ');
export function heading(level: 1 | 2 | 3): Command {
  return level === 1 ? h1 : level === 2 ? h2 : h3;
}
export const bullet: Command = (text, start, end) => prefixLines(text, start, end, '- ');
export const checklist: Command = (text, start, end) => prefixLines(text, start, end, '- [ ] ');
export const quote: Command = (text, start, end) => prefixLines(text, start, end, '> ');

export function commandFor(event: {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
}): Command | null {
  if (!(event.metaKey || event.ctrlKey)) return null;
  const key = event.key.toLowerCase();
  if (!event.altKey && !event.shiftKey && key === 'b') return bold;
  if (!event.altKey && !event.shiftKey && key === 'i') return italic;
  if (event.altKey && !event.shiftKey && key === '1') return h1;
  if (event.altKey && !event.shiftKey && key === '2') return h2;
  if (event.altKey && !event.shiftKey && key === '3') return h3;
  if (!event.altKey && event.shiftKey && (key === '8' || key === '*')) return bullet;
  if (!event.altKey && event.shiftKey && (key === '9' || key === '(')) return checklist;
  if (!event.altKey && event.shiftKey && (key === '.' || key === '>')) return quote;
  return null;
}

import React from 'react';

function inline(text: string, keyPrefix: string): React.ReactNode[] {
  const pattern = /(`[^`\n]+`|\*\*[^*]+\*\*|~~[^~]+~~|\*[^*]+\*|_[^_\n]+_|\[[^\]]+\]\([^)\s]+\))/g;
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let index = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > last) nodes.push(text.slice(last, start));
    const token = match[0];
    const key = `${keyPrefix}-${index++}`;
    if (token.startsWith('`')) nodes.push(<code key={key} style={{ fontFamily: 'var(--mono)' }}>{token.slice(1, -1)}</code>);
    else if (token.startsWith('**')) nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith('~~')) nodes.push(<s key={key}>{token.slice(2, -2)}</s>);
    else if (token.startsWith('*') || token.startsWith('_')) nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    else {
      const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(token);
      const label = link?.[1] ?? token;
      const href = link?.[2] ?? '';
      if (/^https?:\/\//.test(href)) {
        nodes.push(<a key={key} href={href} rel="noreferrer">{label}</a>);
      } else {
        nodes.push(<span key={key}>{label}</span>);
      }
    }
    last = start + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function headingSize(level: number): number {
  return level === 1 ? 28 : level === 2 ? 22 : 18;
}

export function MarkdownView({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const blocks: React.ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    const quote = /^>\s?(.*)$/.exec(line);
    const item = /^(?:[-*+]|\d+[.)])\s+(?:\[([ xX])\]\s+)?(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const Tag = (`h${level}` as 'h1' | 'h2' | 'h3');
      blocks.push(
        <Tag key={i} className="serif" style={{ margin: 0, fontSize: headingSize(level), lineHeight: 1.2 }}>
          {inline(heading[2], `h${i}`)}
        </Tag>,
      );
      i += 1;
      continue;
    }
    if (quote) {
      const quoted: string[] = [];
      while (i < lines.length && lines[i].startsWith('>')) {
        quoted.push(lines[i].replace(/^>\s?/, ''));
        i += 1;
      }
      blocks.push(
        <blockquote key={`q${i}`} style={{ margin: 0, paddingLeft: 12, borderLeft: '1px solid var(--sage-dim)', color: 'var(--ink-2)', fontStyle: 'italic' }}>
          {quoted.map((row, rowIndex) => <div key={rowIndex}>{inline(row, `q${i}-${rowIndex}`)}</div>)}
        </blockquote>,
      );
      continue;
    }
    if (item) {
      const items: { checked: boolean | null; text: string }[] = [];
      while (i < lines.length) {
        const next = /^(?:[-*+]|\d+[.)])\s+(?:\[([ xX])\]\s+)?(.*)$/.exec(lines[i]);
        if (!next) break;
        items.push({ checked: next[1] ? next[1].toLowerCase() === 'x' : null, text: next[2] });
        i += 1;
      }
      blocks.push(
        <ul key={`l${i}`} style={{ margin: 0, paddingLeft: 18 }}>
          {items.map((row, rowIndex) => (
            <li key={rowIndex}>
              {row.checked === null ? null : <span aria-hidden="true">{row.checked ? '☑ ' : '☐ '}</span>}
              {inline(row.text, `l${i}-${rowIndex}`)}
            </li>
          ))}
        </ul>,
      );
      continue;
    }
    if (line.trim() === '') {
      i += 1;
      continue;
    }
    const paragraph: string[] = [];
    while (i < lines.length && lines[i].trim() !== '' && !/^(#{1,3})\s+/.test(lines[i]) && !/^>\s?/.test(lines[i]) && !/^(?:[-*+]|\d+[.)])\s+/.test(lines[i])) {
      paragraph.push(lines[i]);
      i += 1;
    }
    blocks.push(<p key={`p${i}`} style={{ margin: 0 }}>{inline(paragraph.join(' '), `p${i}`)}</p>);
  }
  return <div className="col" style={{ gap: 8 }}>{blocks}</div>;
}

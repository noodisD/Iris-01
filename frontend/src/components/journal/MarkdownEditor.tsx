import React from 'react';
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
import { markdown } from '@codemirror/lang-markdown';
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { tags } from '@lezer/highlight';
import { bold, bullet, checklist, h1, h2, h3, italic, quote, type Command } from './markdownCommands';

const highlight = HighlightStyle.define([
  { tag: tags.heading1, fontWeight: '700', fontSize: '1.7em' },
  { tag: tags.heading2, fontWeight: '700', fontSize: '1.35em' },
  { tag: tags.heading3, fontWeight: '700', fontSize: '1.15em' },
  { tag: tags.strong, fontWeight: '700' },
  { tag: tags.emphasis, fontStyle: 'italic' },
  { tag: tags.strikethrough, textDecoration: 'line-through' },
  { tag: tags.quote, fontStyle: 'italic' },
  { tag: tags.monospace, fontFamily: 'var(--mono)' },
]);

function apply(view: EditorView, command: Command): boolean {
  const sel = view.state.selection.main;
  const next = command(view.state.doc.toString(), sel.from, sel.to);
  view.dispatch({
    changes: { from: 0, to: view.state.doc.length, insert: next.text },
    selection: { anchor: next.start, head: next.end },
  });
  return true;
}

const shortcuts = keymap.of([
  { key: 'Mod-b', run: view => apply(view, bold) },
  { key: 'Mod-i', run: view => apply(view, italic) },
  { key: 'Mod-Alt-1', run: view => apply(view, h1) },
  { key: 'Mod-Alt-2', run: view => apply(view, h2) },
  { key: 'Mod-Alt-3', run: view => apply(view, h3) },
  { key: 'Mod-Shift-8', run: view => apply(view, bullet) },
  { key: 'Mod-Shift-9', run: view => apply(view, checklist) },
  { key: 'Mod-Shift-.', run: view => apply(view, quote) },
]);

export function MarkdownEditor({
  value,
  selection,
  onChange,
  onSelect,
}: {
  value: string;
  selection: { start: number; end: number };
  onChange: (text: string) => void;
  onSelect: (start: number, end: number) => void;
}) {
  const host = React.useRef<HTMLDivElement>(null);
  const viewRef = React.useRef<EditorView | null>(null);
  const onChangeRef = React.useRef(onChange);
  const onSelectRef = React.useRef(onSelect);
  onChangeRef.current = onChange;
  onSelectRef.current = onSelect;

  React.useEffect(() => {
    if (!host.current) return undefined;
    const view = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          history(),
          shortcuts,
          keymap.of([...defaultKeymap, ...historyKeymap]),
          markdown(),
          syntaxHighlighting(highlight),
          EditorView.lineWrapping,
          EditorView.theme({
            '&': { height: '100%', background: 'transparent', color: 'var(--ink)' },
            '.cm-scroller': {
              overflow: 'auto',
              fontFamily: 'var(--serif)',
              fontSize: '20px',
              lineHeight: '1.55',
            },
            '.cm-content': { padding: '8px 0 32px', caretColor: 'var(--sage)', minHeight: '100%' },
            '&.cm-focused': { outline: 'none' },
            '.cm-cursor, .cm-dropCursor': { borderLeftColor: 'var(--sage)' },
            '.cm-gutters': { display: 'none' },
          }),
          EditorView.updateListener.of(update => {
            if (update.docChanged) onChangeRef.current(update.state.doc.toString());
            if (update.selectionSet || update.docChanged) {
              const sel = update.state.selection.main;
              onSelectRef.current(sel.from, sel.to);
            }
          }),
        ],
      }),
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // The editor is created once. Value changes sync in the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  React.useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current === value) return;
    const start = Math.max(0, Math.min(selection.start, value.length));
    const end = Math.max(start, Math.min(selection.end, value.length));
    view.dispatch({
      changes: { from: 0, to: current.length, insert: value },
      selection: { anchor: start, head: end },
    });
  }, [value, selection.start, selection.end]);

  return <div ref={host} data-testid="journal-editor" style={{ height: '100%', minHeight: 280 }} />;
}

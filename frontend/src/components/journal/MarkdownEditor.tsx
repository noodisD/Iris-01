import React from 'react';
import { autocompletion, type CompletionContext, type CompletionResult } from '@codemirror/autocomplete';
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
import { markdown } from '@codemirror/lang-markdown';
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView, keymap, placeholder } from '@codemirror/view';
import { tags } from '@lezer/highlight';
import { bold, bullet, checklist, h1, h2, h3, italic, quote, type Command } from './markdownCommands';

/** Shown in the empty pane: where to write, and that Markdown works. */
export const JOURNAL_PLACEHOLDER = 'Write about your day…   **bold**  # heading  - list  - [ ] task  > quote';

const highlight = HighlightStyle.define([
  { tag: tags.heading1, fontWeight: '700', fontSize: '1.7em' },
  { tag: tags.heading2, fontWeight: '700', fontSize: '1.35em' },
  { tag: tags.heading3, fontWeight: '700', fontSize: '1.15em' },
  { tag: tags.strong, fontWeight: '700' },
  { tag: tags.emphasis, fontStyle: 'italic' },
  { tag: tags.strikethrough, textDecoration: 'line-through' },
  { tag: tags.quote, fontStyle: 'italic' },
  { tag: tags.monospace, fontFamily: 'var(--font-ui)' },
]);

/**
 * After `[[`, offer the titles a page can link to, as Obsidian does. Picking
 * one writes the title and closes the link.
 */
function wikilinkSource(targets: () => string[]) {
  return (context: CompletionContext): CompletionResult | null => {
    const before = context.matchBefore(/\[\[[^\[\]|\n]*/);
    if (!before) return null;
    const from = before.from + 2;
    const closed = context.state.sliceDoc(context.pos, context.pos + 2) === ']]';
    return {
      from,
      filter: true,
      options: targets().map(label => ({ label, apply: closed ? label : `${label}]]` })),
    };
  };
}

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
  label = 'journal entry',
  placeholderText = JOURNAL_PLACEHOLDER,
  linkTargets,
  fontSize = 20,
  minHeight = 280,
}: {
  value: string;
  selection: { start: number; end: number };
  onChange: (text: string) => void;
  onSelect: (start: number, end: number) => void;
  /** The editable area's accessible name. */
  label?: string;
  placeholderText?: string;
  /** Titles offered after `[[`. Without it, `[[` is plain text. */
  linkTargets?: string[];
  fontSize?: number;
  minHeight?: number;
}) {
  const host = React.useRef<HTMLDivElement>(null);
  const viewRef = React.useRef<EditorView | null>(null);
  const onChangeRef = React.useRef(onChange);
  const onSelectRef = React.useRef(onSelect);
  onChangeRef.current = onChange;
  onSelectRef.current = onSelect;
  const targetsRef = React.useRef(linkTargets ?? []);
  targetsRef.current = linkTargets ?? [];

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
          placeholder(placeholderText),
          ...(linkTargets ? [autocompletion({ override: [wikilinkSource(() => targetsRef.current)], icons: false })] : []),
          // The editable area is named for screen readers, like the fallback textarea.
          EditorView.contentAttributes.of({ 'aria-label': label, 'aria-multiline': 'true' }),
          EditorView.theme({
            '&': { height: '100%', background: 'transparent', color: 'var(--petal)' },
            '.cm-scroller': {
              overflow: 'auto',
              fontFamily: 'var(--font-read)',
              fontSize: `${fontSize}px`,
              lineHeight: '1.55',
            },
            '.cm-content': { padding: '8px 0 32px', caretColor: 'var(--iris)', minHeight: '100%' },
            '&.cm-focused': { outline: 'none' },
            '.cm-cursor, .cm-dropCursor': { borderLeftColor: 'var(--iris)' },
            '.cm-gutters': { display: 'none' },
            '.cm-placeholder': { color: 'var(--petal-3)', fontStyle: 'italic' },
            '.cm-tooltip.cm-tooltip-autocomplete': {
              background: 'var(--dusk)', border: '1px solid var(--mist-2)', borderRadius: '8px', overflow: 'hidden',
            },
            '.cm-tooltip.cm-tooltip-autocomplete > ul': {
              fontFamily: 'var(--font-read)', fontSize: '15px', maxWidth: 'min(560px, 90vw)', maxHeight: '16em',
            },
            '.cm-tooltip.cm-tooltip-autocomplete > ul > li': { padding: '6px 10px', whiteSpace: 'normal', lineHeight: '1.35' },
            '.cm-tooltip.cm-tooltip-autocomplete > ul > li[aria-selected]': { background: 'var(--iris-soft)', color: 'var(--petal)' },
            '.cm-completionMatchedText': { textDecoration: 'none', color: 'var(--iris-text)' },
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

  return <div ref={host} data-testid="journal-editor" style={{ height: '100%', minHeight }} />;
}

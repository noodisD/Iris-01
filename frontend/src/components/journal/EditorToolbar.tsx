import type { Command } from './markdownCommands';
import { bold, bullet, checklist, heading, italic, quote } from './markdownCommands';

const COMMANDS: { label: string; title: string; command: Command }[] = [
  { label: 'B', title: 'Bold', command: bold },
  { label: 'I', title: 'Italic', command: italic },
  { label: 'H1', title: 'Heading 1', command: heading(1) },
  { label: 'H2', title: 'Heading 2', command: heading(2) },
  { label: 'H3', title: 'Heading 3', command: heading(3) },
  { label: '• List', title: 'Bullet', command: bullet },
  { label: '[ ] Task', title: 'Checklist', command: checklist },
  { label: '“ Quote', title: 'Quote', command: quote },
];

export function EditorToolbar({ onCommand }: { onCommand: (command: Command) => void }) {
  return (
    <div className="row" role="toolbar" aria-label="formatting"
      style={{ gap: 2, flexWrap: 'wrap', padding: '6px 8px', borderBottom: '1px solid var(--line-soft)' }}>
      {COMMANDS.map(item => (
        <button
          key={item.title}
          type="button"
          className="btn ghost"
          title={item.title}
          aria-label={item.title}
          onMouseDown={event => event.preventDefault()}
          onClick={() => onCommand(item.command)}
          style={{ minWidth: 34, padding: '4px 9px', fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--ink-2)' }}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

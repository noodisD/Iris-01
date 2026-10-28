import React from 'react';
import type { JournalEntry } from '@/types/api';
import { Button } from '@/ui';
import { MarkdownView } from './MarkdownView';
import { SessionView } from './SessionView';
import styles from './EntryBody.module.css';

const LANGUAGES: Record<string, string> = {
  pl: 'Polish', de: 'German', es: 'Spanish', fr: 'French', it: 'Italian', uk: 'Ukrainian',
};

/**
 * An entry's words. Writing in another language shows its English version
 * first, the one IRIS reads (ADR-0036), with the original one tap away.
 */
export function EntryBody({ entry, textClass }: { entry: JournalEntry; textClass?: string }) {
  const [original, setOriginal] = React.useState(false);
  const translation = entry.translation;
  const language = translation ? LANGUAGES[translation.from] ?? translation.from : '';
  const english = translation && !original;
  const session = english ? translation.session ?? null : entry.session ?? null;
  const text = english ? translation.text : entry.text ?? entry.lines.join('\n');
  return (
    <>
      {translation && (
        <p className={styles.language}>
          {english ? `Translated from ${language}.` : `The original, in ${language}.`}{' '}
          <Button size="sm" variant="quiet" onClick={() => setOriginal(shown => !shown)}>
            {english ? `Show the ${language}` : 'Show the English'}
          </Button>
        </p>
      )}
      {session
        ? <SessionView session={session} />
        : entry.format === 'markdown' && !english
          ? <div className={textClass}><MarkdownView text={text} /></div>
          : <div className={textClass}>{text}</div>}
    </>
  );
}

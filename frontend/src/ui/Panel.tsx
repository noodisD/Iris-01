import type React from 'react';
import styles from './Panel.module.css';

/**
 * A raised surface, for things the owner acts on: a pattern to judge, an entry,
 * a pending batch. `tone="confirmed"` marks something the owner confirmed.
 */
export function Panel({ children, tone, as: Tag = 'div', className, ...rest }: React.HTMLAttributes<HTMLElement> & {
  tone?: 'confirmed' | 'quiet'; as?: 'div' | 'article' | 'section' | 'li';
}) {
  return (
    <Tag className={[styles.panel, tone ? styles[tone] : '', className].filter(Boolean).join(' ')} {...rest}>
      {children}
    </Tag>
  );
}

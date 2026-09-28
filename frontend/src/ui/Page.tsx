import type React from 'react';
import styles from './Page.module.css';

type Width = 'reading' | 'standard' | 'wide';

/**
 * Every screen's frame: one left edge, one header, one set of widths.
 * `lead` is a line above the title only when it carries information (a date).
 */
export function Page({ title, lead, description, actions, width = 'standard', children, workspace = false }: {
  title: React.ReactNode;
  lead?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  width?: Width;
  /** Fill the app frame. Used by the Observatory system map. */
  workspace?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={`${styles.page} ${styles[width]}${workspace ? ` ${styles.workspace}` : ''}`}>
      <header className={styles.header}>
        <div className={styles.titles}>
          {lead && <p className={styles.lead}>{lead}</p>}
          <h1 className={styles.title}>{title}</h1>
          {description && <p className={styles.description}>{description}</p>}
        </div>
        {actions && <div className={styles.actions}>{actions}</div>}
      </header>
      <div className={workspace ? styles.workspaceBody : styles.body}>{children}</div>
    </div>
  );
}

/** A titled part of a page. Not a card: sections are plain unless you act on them. */
export function Section({ title, description, actions, children }: {
  title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <section className={styles.section} aria-label={typeof title === 'string' ? title : undefined}>
      <div className={styles.sectionHead}>
        <div>
          <h2 className={styles.sectionTitle}>{title}</h2>
          {description && <p className={styles.sectionDescription}>{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

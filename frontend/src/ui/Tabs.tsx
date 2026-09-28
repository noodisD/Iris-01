import * as RadixTabs from '@radix-ui/react-tabs';
import type React from 'react';
import styles from './Tabs.module.css';

/**
 * Tabs with keyboard support (arrow keys) and linked panels. Controlled, so a
 * screen can keep the tab in the URL.
 */
export function Tabs<T extends string>({ label, value, onChange, tabs, children, fill = false }: {
  label: string;
  value: T;
  onChange: (value: T) => void;
  tabs: { value: T; label: React.ReactNode }[];
  children: React.ReactNode;
  /** Let the active panel fill the remaining height. Inactive panels stay hidden. */
  fill?: boolean;
}) {
  return (
    <RadixTabs.Root value={value} onValueChange={next => onChange(next as T)} className={fill ? `${styles.root} ${styles.fill}` : styles.root}>
      <RadixTabs.List aria-label={label} className={styles.list}>
        {tabs.map(tab => (
          <RadixTabs.Trigger key={tab.value} value={tab.value} className={styles.trigger}>{tab.label}</RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      {children}
    </RadixTabs.Root>
  );
}

export function TabPanel({ value, children }: { value: string; children: React.ReactNode }) {
  return <RadixTabs.Content value={value} className={styles.panel}>{children}</RadixTabs.Content>;
}

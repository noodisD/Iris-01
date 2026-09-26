import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type React from 'react';
import styles from './Sheet.module.css';

/** A panel that slides over the page: focus is kept inside, Escape closes it. */
export function Sheet({ open, onOpenChange, title, side = 'bottom', children }: {
  open: boolean; onOpenChange: (open: boolean) => void; title: string;
  side?: 'bottom' | 'left'; children: React.ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className={styles.overlay} />
        <Dialog.Content className={`${styles.content} ${styles[side]}`} aria-describedby={undefined}>
          <div className={styles.head}>
            <Dialog.Title className={styles.title}>{title}</Dialog.Title>
            <Dialog.Close className={styles.close} aria-label="Close"><X size={18} /></Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

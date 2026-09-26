import type React from 'react';
import styles from './DataTable.module.css';

export interface Column<Row> {
  key: string;
  header: React.ReactNode;
  cell: (row: Row) => React.ReactNode;
  numeric?: boolean;
}

/** A readable table: numbers right-aligned in tabular figures; scrolls sideways on phones. */
export function DataTable<Row>({ label, columns, rows, rowKey, empty }: {
  label: string; columns: Column<Row>[]; rows: Row[]; rowKey: (row: Row) => string; empty?: React.ReactNode;
}) {
  if (rows.length === 0 && empty) return <>{empty}</>;
  return (
    <div className={styles.wrap} role="region" aria-label={label} tabIndex={0}>
      <table className={styles.table}>
        <thead>
          <tr>{columns.map(c => <th key={c.key} scope="col" className={c.numeric ? styles.num : undefined}>{c.header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={rowKey(row)}>
              {columns.map(c => <td key={c.key} className={c.numeric ? styles.num : undefined}>{c.cell(row)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

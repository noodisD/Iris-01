/** The kit's behaviour: what the owner can do with keyboard and pointer. */
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ChoiceGroup, DataTable, Field, Page, TabPanel, Tabs } from '@/ui';
import { PhoneNav } from '@/components/PhoneNav';

const VERDICTS = [{ value: 'yes', label: 'Rings true' }, { value: 'no', label: "Doesn't" }] as const;

describe('ChoiceGroup', () => {
  it('picks one, and clears it when picked again if clearable', () => {
    const onChange = vi.fn();
    const { rerender } = render(<ChoiceGroup label="Verdict" options={[...VERDICTS]} value={null} onChange={onChange} clearable />);
    fireEvent.click(screen.getByRole('radio', { name: 'Rings true' }));
    expect(onChange).toHaveBeenLastCalledWith('yes');
    rerender(<ChoiceGroup label="Verdict" options={[...VERDICTS]} value="yes" onChange={onChange} clearable />);
    expect(screen.getByRole('radio', { name: 'Rings true' })).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(screen.getByRole('radio', { name: 'Rings true' }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it('keeps the answer when it is not clearable', () => {
    const onChange = vi.fn();
    render(<ChoiceGroup label="Verdict" options={[...VERDICTS]} value="yes" onChange={onChange} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Rings true' }));
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe('Tabs', () => {
  it('shows the chosen panel and names the list', () => {
    render(
      <Tabs label="Journal" value="write" onChange={() => {}} tabs={[{ value: 'write', label: 'Write' }, { value: 'entries', label: 'Entries' }]}>
        <TabPanel value="write">writing</TabPanel>
        <TabPanel value="entries">history</TabPanel>
      </Tabs>,
    );
    expect(screen.getByRole('tablist', { name: 'Journal' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Write' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('writing')).toBeInTheDocument();
    expect(screen.queryByText('history')).toBeNull();
  });
});

describe('Field', () => {
  it('names its control by the label and describes it by the hint and error', () => {
    render(<Field label="Habit name" hint="Short is better" error="Required"><input /></Field>);
    const input = screen.getByRole('textbox', { name: 'Habit name' });
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input.getAttribute('aria-describedby')?.split(' ')).toHaveLength(2);
    expect(screen.getByRole('alert')).toHaveTextContent('Required');
  });
});

describe('DataTable', () => {
  it('shows the empty message instead of an empty table', () => {
    render(<DataTable label="Days" columns={[]} rows={[]} rowKey={() => ''} empty={<p>No days yet.</p>} />);
    expect(screen.getByText('No days yet.')).toBeInTheDocument();
  });
});

describe('Page', () => {
  it('has one level-one heading, the title', () => {
    render(<Page title="Today" lead="Saturday">body</Page>);
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Today');
  });
});

describe('PhoneNav', () => {
  it('offers the daily three and a menu with every section', () => {
    render(<MemoryRouter initialEntries={['/today']}><PhoneNav /></MemoryRouter>);
    for (const name of ['Today', 'Journal', 'Chat']) expect(screen.getByRole('link', { name })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Menu' }));
    const dialog = screen.getByRole('dialog', { name: 'Iris' });
    expect(dialog).toHaveTextContent('Your data');
    expect(screen.getAllByRole('link', { name: 'Sensors' }).length).toBeGreaterThan(0);
  });
});

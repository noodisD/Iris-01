/** The menu folds to a strip with an arrow, opens again, and remembers which. */
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/hooks/useData', () => ({ useUser: () => ({ data: { name: 'Owner', dayInJourney: 3 } }) }));
vi.mock('@/hooks/useIrisState', () => ({ useIrisStore: () => ({ vibe: 'auto' }), applyOrbVibe: () => {} }));
vi.mock('@/components/primitives', () => ({ Orb: () => <span data-testid="orb" /> }));

import { Sidebar } from './Sidebar';

function show() {
  return render(<MemoryRouter><Sidebar /></MemoryRouter>);
}

// The test environment has no localStorage; a small in-memory one stands in.
function memoryStorage() {
  const items = new Map<string, string>();
  return {
    getItem: (k: string) => items.get(k) ?? null,
    setItem: (k: string, v: string) => { items.set(k, v); },
  };
}

describe('Sidebar', () => {
  beforeEach(() => { vi.stubGlobal('localStorage', memoryStorage()); });

  it('folds to the orb and an arrow, and opens again', () => {
    show();
    fireEvent.click(screen.getByRole('button', { name: 'Fold the menu' }));
    expect(screen.queryByRole('link', { name: 'Insights' })).toBeNull();
    expect(screen.getByTestId('orb')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open the menu' }));
    expect(screen.getByRole('link', { name: 'Insights' })).toBeInTheDocument();
  });

  it('remembers that it was folded', () => {
    const first = show();
    fireEvent.click(screen.getByRole('button', { name: 'Fold the menu' }));
    first.unmount();
    show();
    expect(screen.getByRole('button', { name: 'Open the menu' })).toBeInTheDocument();
  });

  it('opens when storage is unavailable', () => {
    vi.stubGlobal('localStorage', { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); } });
    show();
    expect(screen.getByRole('link', { name: 'Insights' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Fold the menu' }));
    expect(screen.getByRole('button', { name: 'Open the menu' })).toBeInTheDocument();
  });
});

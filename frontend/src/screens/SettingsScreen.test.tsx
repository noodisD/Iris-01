/** Settings: one topic per tab, the phone summarised before its controls, and QR codes only on request. */
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/hooks/useData', () => ({
  useKnowledge: () => ({ data: [
    { id: 'k1', fact: 'Prefers mornings for planning', source: 'pattern', ageDays: 12, editable: true },
    { id: 'k2', fact: 'Keeps a garden', source: 'confirmed', ageDays: 40, editable: true },
  ], isLoading: false, isError: false, refetch: vi.fn() }),
  useAnalysisPreferences: () => ({ data: {
    minConfidence: 'medium', maxItems: 5, enabledEngines: null, availableEngines: ['trajectory', 'tension'],
  } }),
}));
vi.mock('@/components/QrCode', () => ({ QrCode: ({ label }: { label: string }) => <div role="img" aria-label={label} /> }));
vi.mock('@/api/settings', () => ({
  forgetFact: vi.fn(), updateAnalysisPreferences: vi.fn(), resetAnalysisPreferences: vi.fn(),
  pairMobile: vi.fn(), unpairMobile: vi.fn(), phonePairingCode: () => 'code',
  getMobileConnection: async () => ({
    lan_url: 'https://100.64.0.9:8765', public_key_sha256: 'ab'.repeat(32), listener: 'listening', listener_error: null,
    paired: true, paired_at: null, last_seen_at: '2026-09-25T18:00:00Z', last_intake_at: null, pending_batches: 2, last_rejection: null,
  }),
}));

import { SettingsScreen } from './SettingsScreen';

function show(path = '/settings') {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}><SettingsScreen /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Settings', () => {
  it('opens on what IRIS may bring up, with the other topics as tabs', () => {
    show();
    expect(screen.getByRole('tab', { name: 'Conversation' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('region', { name: 'What IRIS may bring up' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Notes · 2' })).toBeInTheDocument();
    expect(screen.queryByText(/Prefers mornings/)).toBeNull();
  });

  it('summarises the phone first and shows a QR code only when asked', async () => {
    show('/settings?tab=phone');
    expect(await screen.findByText('Phone paired and in touch')).toBeInTheDocument();
    expect(screen.getByText('2 sensor batches to review')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'IRIS address QR code' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show address QR' }));
    expect(screen.getByRole('img', { name: 'IRIS address QR code' })).toBeInTheDocument();
  });

  it('lists the notes under their own tab, each removable', () => {
    show('/settings?tab=notes');
    expect(screen.getByText(/Prefers mornings for planning/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /forget|stop counting/ })).toHaveLength(2);
  });
});

/**
 * Talk mode shows what talking costs before anything is sent, then says what
 * IRIS is doing and offers only the controls that apply (ADR-0025).
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { TalkPhase } from '@/lib/talk';

vi.mock('@/api/voice', () => ({
  getVoiceEstimate: async () => ({ model: 'gpt-5.6-terra', transcriptionModel: 't', speechModel: 's', tokensIn: 5000, perTurn: 'about $0.013 a turn' }),
}));

import { TalkIntro, TalkMode } from './TalkMode';

function withQueries(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

function fakeTalk(phase: TalkPhase, error: string | null = null) {
  return {
    state: { phase, error },
    levelRef: React.createRef<HTMLDivElement>(),
    start: vi.fn(), end: vi.fn(), pause: vi.fn(), resume: vi.fn(), stopSpeaking: vi.fn(),
  };
}

describe('before talking', () => {
  it('says what is sent and what a turn costs, and sends nothing until Start', async () => {
    const onStart = vi.fn();
    withQueries(<TalkIntro onStart={onStart} onCancel={vi.fn()} />);
    expect(screen.getByRole('dialog', { name: 'Talk with IRIS' })).toHaveTextContent('the audio is not');
    expect(await screen.findByText('about $0.013 a turn, on gpt-5.6-terra.')).toBeInTheDocument();
    expect(onStart).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Start talking' }));
    expect(onStart).toHaveBeenCalledOnce();
  });
});

describe('talking', () => {
  it('says what IRIS is doing', () => {
    const { rerender } = render(<TalkMode talk={fakeTalk('listening')} />);
    expect(screen.getByText('Listening')).toBeInTheDocument();
    rerender(<TalkMode talk={fakeTalk('thinking')} />);
    expect(screen.getByText('Thinking')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pause listening' })).toBeDisabled();
    rerender(<TalkMode talk={fakeTalk('speaking')} />);
    expect(screen.getByText('IRIS is speaking')).toBeInTheDocument();
  });

  it('stops IRIS speaking with the button or Esc', () => {
    const talk = fakeTalk('speaking');
    render(<TalkMode talk={talk} />);
    fireEvent.click(screen.getByRole('button', { name: 'Stop speaking' }));
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(talk.stopSpeaking).toHaveBeenCalledTimes(2);
  });

  it('pauses and resumes listening with Space', () => {
    const listening = fakeTalk('listening');
    const { unmount } = render(<TalkMode talk={listening} />);
    fireEvent.keyDown(window, { key: ' ' });
    expect(listening.pause).toHaveBeenCalledOnce();
    unmount();
    const paused = fakeTalk('paused');
    render(<TalkMode talk={paused} />);
    expect(screen.getByRole('button', { name: 'Resume listening' })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: ' ' });
    expect(paused.resume).toHaveBeenCalledOnce();
  });

  it('explains a problem and offers to try again', () => {
    const talk = fakeTalk('error', 'IRIS needs your microphone. Allow it for this site in the browser, then start again.');
    render(<TalkMode talk={talk} />);
    expect(screen.getByRole('alert')).toHaveTextContent('IRIS needs your microphone');
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(talk.start).toHaveBeenCalledOnce();
  });
});

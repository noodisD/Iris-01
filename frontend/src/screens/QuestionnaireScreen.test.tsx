/**
 * The questionnaire screen: progress per section, the Polish one tap away, a
 * draft saved as typed, and the cost shown before a section is added.
 * Every question here is invented.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Questionnaire, QuestionnaireQuestion } from '@/types/api';

const state = vi.hoisted(() => ({ data: null as unknown, calls: [] as [string, unknown][] }));

vi.mock('@/hooks/useQuestionnaire', () => ({
  useQuestionnaire: () => ({ data: state.data, isLoading: false, error: null, refetch: () => {} }),
  useSectionEstimate: () => ({ data: { answers: 1, dollars: 0.12, text: 'Adding 1 answer sends it to OpenAI: at most about $0.12.' } }),
  useAnswerHistory: () => ({ data: [] }),
  useSuggestEstimate: () => ({ data: { questions: 1, dollars: 0.01, text: 'Looks through your writing: about $0.01.' } }),
  useQuestionnaireActions: () => new Proxy({}, {
    get: (_t, op) => ({ mutate: (v: unknown) => state.calls.push([String(op), v]), isPending: false }),
  }),
}));

import { QuestionnaireScreen } from './QuestionnaireScreen';

const question = (over: Partial<QuestionnaireQuestion>): QuestionnaireQuestion => ({
  id: 'q1', number: 1, text: 'Where did you grow up?', textPl: 'Gdzie dorastałeś?', status: 'unanswered',
  answer: '', source: null, transcript: null, revising: false, addedAt: null, history: 0, ...over,
});

function questionnaire(questions: QuestionnaireQuestion[]): Questionnaire {
  return {
    id: 'baseline', title: 'Questionnaire', titlePl: 'Ankieta', version: 'test', about: null, aboutPl: null,
    sections: [
      { id: 'home', title: 'Home', titlePl: 'Dom', intro: 'About home.', introPl: 'O domu.', questions,
        counts: { unanswered: 1, draft: questions.filter(q => q.status === 'draft').length, added: 0, skipped: 0, total: questions.length } },
      { id: 'work', title: 'Work', titlePl: 'Praca', intro: '', introPl: '', questions: [],
        counts: { unanswered: 0, draft: 0, added: 0, skipped: 0, total: 0 } },
    ],
  };
}

beforeEach(() => { state.calls = []; vi.useRealTimers(); });

describe('the questionnaire screen', () => {
  it('lists sections with progress and shows the Polish on request', () => {
    state.data = questionnaire([question({}), question({ id: 'q2', number: 2, text: 'What calms you?', status: 'draft', answer: 'Walking.' })]);
    render(<QuestionnaireScreen />);
    expect(screen.getByRole('button', { name: /Home 1 of 2/ })).toHaveAttribute('aria-current', 'true');
    expect(screen.queryByText('Gdzie dorastałeś?')).toBeNull();
    fireEvent.click(screen.getAllByRole('button', { name: 'Show the Polish' })[0]);
    expect(screen.getByText('Gdzie dorastałeś?')).toBeInTheDocument();
  });

  it('saves a draft shortly after typing stops', () => {
    vi.useFakeTimers();
    state.data = questionnaire([question({})]);
    render(<QuestionnaireScreen />);
    fireEvent.change(screen.getByLabelText('Your answer to question 1'), { target: { value: 'By a lake.' } });
    act(() => { vi.advanceTimersByTime(1500); });
    expect(state.calls).toEqual([['save', { id: 'q1', answer: 'By a lake.', source: 'form', transcript: undefined }]]);
  });

  it('shows the cost before a section is added, and adds on the click', () => {
    state.data = questionnaire([question({ status: 'draft', answer: 'By a lake.' })]);
    render(<QuestionnaireScreen />);
    expect(screen.getByText('Adding 1 answer sends it to OpenAI: at most about $0.12.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Add 1 answer to IRIS' }));
    expect(state.calls).toContainEqual(['add', 'home']);
  });

  it('lets a question be skipped', () => {
    state.data = questionnaire([question({})]);
    render(<QuestionnaireScreen />);
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
    expect(state.calls).toEqual([['skip', { id: 'q1', skipped: true }]]);
  });
});

describe('suggestions from your writing', () => {
  it('shows the cost first and asks on the click', () => {
    state.data = questionnaire([question({})]);
    render(<QuestionnaireScreen />);
    expect(screen.getByText('Looks through your writing: about $0.01.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Suggest answers from my writing' }));
    expect(state.calls).toContainEqual(['suggest', 'home']);
  });

  it('marks a suggested draft as suggested', () => {
    state.data = questionnaire([question({ status: 'draft', source: 'suggested', answer: '“By a lake.” (journal, 2025-03-12)' })]);
    render(<QuestionnaireScreen />);
    expect(screen.getByText('Suggested')).toBeInTheDocument();
  });
});

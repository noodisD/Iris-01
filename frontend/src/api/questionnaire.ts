/**
 * The baseline questionnaire (ADR-0029).
 *   GET  /api/questionnaire                              → Questionnaire (404 when not installed)
 *   PUT  /api/questionnaire/answers/:qid                 → QuestionnaireQuestion (a draft; nothing sent)
 *   POST /api/questionnaire/answers/:qid/skip            → QuestionnaireQuestion
 *   GET  /api/questionnaire/answers/:qid/history         → { versions }
 *   GET  /api/questionnaire/sections/:sid/estimate       → { answers, dollars, text }
 *   POST /api/questionnaire/sections/:sid/add            → { added }   (the owner's click)
 *   GET  /api/questionnaire/sections/:sid/suggest/estimate → { questions, dollars, text }
 *   POST /api/questionnaire/sections/:sid/suggest       → { suggested, nothing, failed } (the owner's click)
 *   POST /api/questionnaire/interview/:qid               → InterviewStep
 */

import { api } from './client';
import type { InterviewStep, InterviewTurn, Questionnaire, QuestionnaireQuestion } from '@/types/api';

export interface AnswerVersion { version: number; answer: string; source: string; status: string; addedAt: string | null }

export const getQuestionnaire = () => api.get<Questionnaire>('/questionnaire');

export const saveAnswer = (id: string, body: { answer: string; source?: 'form' | 'interview'; transcript?: InterviewTurn[] }) =>
  api.put<QuestionnaireQuestion>(`/questionnaire/answers/${id}`, body);

export const skipQuestion = (id: string, skipped: boolean) =>
  api.post<QuestionnaireQuestion>(`/questionnaire/answers/${id}/skip`, { skipped });

export const answerHistory = async (id: string) =>
  (await api.get<{ versions: AnswerVersion[] }>(`/questionnaire/answers/${id}/history`)).versions;

export const sectionEstimate = (id: string) =>
  api.get<{ answers: number; dollars: number | null; text: string }>(`/questionnaire/sections/${id}/estimate`);

export const addSection = (id: string) => api.post<{ added: number }>(`/questionnaire/sections/${id}/add`);

export const interviewStep = (id: string, messages: InterviewTurn[]) =>
  api.post<InterviewStep>(`/questionnaire/interview/${id}`, { messages });

export const suggestEstimate = (id: string) =>
  api.get<{ questions: number; dollars: number | null; text: string }>(`/questionnaire/sections/${id}/suggest/estimate`);

export const suggestSection = (id: string) =>
  api.post<{ suggested: number; nothing: number; failed: number }>(`/questionnaire/sections/${id}/suggest`);

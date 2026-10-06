import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '@/lib/queryClient';
import * as qApi from '@/api/questionnaire';
import type { InterviewTurn } from '@/types/api';

export const useQuestionnaire = () =>
  useQuery({ queryKey: qk.questionnaire, queryFn: qApi.getQuestionnaire, retry: false });

export const useSectionEstimate = (id: string, drafts: number) =>
  useQuery({ queryKey: [...qk.questionnaireEstimate(id), drafts], queryFn: () => qApi.sectionEstimate(id),
             enabled: drafts > 0 });

export const useAnswerHistory = (id: string, open: boolean) =>
  useQuery({ queryKey: qk.questionnaireHistory(id), queryFn: () => qApi.answerHistory(id), enabled: open });

export function useQuestionnaireActions() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: qk.questionnaire });
  return {
    save: useMutation({
      mutationFn: (v: { id: string; answer: string; source?: 'form' | 'interview'; transcript?: InterviewTurn[] }) =>
        qApi.saveAnswer(v.id, { answer: v.answer, source: v.source, transcript: v.transcript }),
      onSuccess: refresh,
    }),
    skip: useMutation({
      mutationFn: (v: { id: string; skipped: boolean }) => qApi.skipQuestion(v.id, v.skipped),
      onSuccess: refresh,
    }),
    add: useMutation({ mutationFn: qApi.addSection, onSuccess: refresh }),
  };
}

import { api } from './client';
import type {
  ConfirmIdeaBody, IdeaCritique, IdeaDetail, IdeaDomain, IdeaPosition, IdeaRun, IdeaSummary,
  IdeasFramework, IdeasReview,
} from '@/types/api';

export function getIdeasFramework(): Promise<IdeasFramework> {
  return api.get('/ideas/framework');
}

export function getIdeaReview(): Promise<IdeasReview> {
  return api.get('/ideas/review');
}

export function getIdea(id: string): Promise<IdeaDetail> {
  return api.get(`/ideas/${id}`);
}

export function discoverIdeas(): Promise<{ run: IdeaRun }> {
  return api.post('/ideas/discover');
}

export function confirmIdea(id: string, body: ConfirmIdeaBody): Promise<{ id: string; status: 'active' }> {
  return api.post(`/ideas/${id}/confirm`, body);
}

export function rejectIdea(id: string): Promise<{ id: string; status: 'rejected' }> {
  return api.post(`/ideas/${id}/reject`);
}

export function rejectIdeaCitations(id: string, citationIds: string[]): Promise<{ id: string; rejected: number }> {
  return api.post(`/ideas/${id}/citations/reject`, { citationIds });
}

export function updateIdea(
  id: string,
  body: { position?: IdeaPosition; domain?: IdeaDomain },
): Promise<IdeaSummary> {
  return api.patch(`/ideas/${id}`, body);
}

export function discoverIdeaLinks(id: string): Promise<{ run: IdeaRun }> {
  return api.post(`/ideas/${id}/links/discover`);
}

export function confirmIdeaLink(id: string): Promise<{ id: string; status: 'accepted' }> {
  return api.post(`/ideas/links/${id}/confirm`);
}

export function rejectIdeaLink(id: string): Promise<{ id: string; status: 'rejected' }> {
  return api.post(`/ideas/links/${id}/reject`);
}

export function critiqueIdea(id: string): Promise<{ critique: IdeaCritique }> {
  return api.post(`/ideas/${id}/critique`);
}

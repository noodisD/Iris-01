import type { IdeaDomain } from '@/types/api';

/** The areas an idea can belong to, in the order they are shown. */
export const AREAS: { value: IdeaDomain; label: string }[] = [
  { value: 'life', label: 'Life' },
  { value: 'philosophy', label: 'Philosophy' },
  { value: 'ethics', label: 'Ethics' },
  { value: 'politics', label: 'Politics' },
  { value: 'economics', label: 'Economics' },
  { value: 'markets', label: 'Markets' },
  { value: 'learning', label: 'Learning' },
  { value: 'other', label: 'Other' },
];

/**
 * One colour per area, the same on the map, its index and the area chips, so
 * the colours explain themselves. Categorical, tuned to the night background;
 * Life is gold because it is the owner's own cross-area principle. Violet is
 * left out: in Iris it means "act".
 */
export const AREA_COLOR: Record<IdeaDomain, string> = {
  life: '#e3c26b',
  philosophy: '#9aa6e0',
  ethics: '#8fc4a8',
  politics: '#c79ad9',
  economics: '#d9a877',
  markets: '#d98a8a',
  learning: '#7fbcc9',
  other: '#8c89a6',
};

export function areaLabel(value: IdeaDomain): string {
  return AREAS.find(area => area.value === value)?.label ?? value;
}

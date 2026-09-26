/**
 * Global Iris state — the orb's vibe.
 * Persists user choices to localStorage so a hard reload feels stable.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type OrbVibe = 'auto' | 'calm' | 'low' | 'high' | 'cool' | 'dim';

interface IrisState {
  vibe: OrbVibe;
  setVibe: (v: OrbVibe) => void;
}

export const useIrisStore = create<IrisState>()(
  persist(
    (set) => ({
      vibe: 'auto',
      setVibe: (vibe) => set({ vibe }),
    }),
    { name: 'iris-state' },
  ),
);

/** Apply orb CSS variables based on current vibe + active screen. */
export function applyOrbVibe(vibe: OrbVibe, screenFallback: Exclude<OrbVibe, 'auto'> = 'calm') {
  const effective: Exclude<OrbVibe, 'auto'> = vibe === 'auto' ? screenFallback : vibe;
  // The lens: inner light, iris, outer ring, glow, breathing rate. All in the
  // violet family so the one bold element stays one colour story.
  const palettes: Record<Exclude<OrbVibe, 'auto'>, [string, string, string, string, string]> = {
    calm: ['#d6d0ff', '#8b7fd6', '#3d3570', 'rgba(139,127,214,0.35)', '4s'],
    low:  ['#f0cfe0', '#b784b8', '#4f3050', 'rgba(183,132,184,0.35)', '6.5s'],
    high: ['#f6e6b8', '#c9a2d8', '#5a3f6e', 'rgba(227,194,107,0.30)', '2.4s'],
    cool: ['#d4dcff', '#7f93dc', '#2f3a6e', 'rgba(127,147,220,0.35)', '5.5s'],
    dim:  ['#6a6788', '#3f3d5c', '#22213a', 'rgba(80,78,120,0.25)',   '7s'],
  };
  const [a, b, c, g, r] = palettes[effective];
  const root = document.documentElement;
  root.style.setProperty('--orb-hue-a', a);
  root.style.setProperty('--orb-hue-b', b);
  root.style.setProperty('--orb-hue-c', c);
  root.style.setProperty('--orb-glow', g);
  root.style.setProperty('--orb-rate', r);
}

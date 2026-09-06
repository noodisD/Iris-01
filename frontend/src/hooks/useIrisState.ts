/**
 * Global Iris state — orb vibe, day-in-journey, tone overrides.
 * Persists user choices to localStorage so a hard reload feels stable.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type OrbVibe = 'auto' | 'calm' | 'low' | 'high' | 'cool' | 'dim';

interface IrisState {
  vibe: OrbVibe;
  dayOverride: number | null;     // null = use server value
  setVibe: (v: OrbVibe) => void;
  setDayOverride: (d: number | null) => void;
}

export const useIrisStore = create<IrisState>()(
  persist(
    (set) => ({
      vibe: 'auto',
      dayOverride: null,
      setVibe: (vibe) => set({ vibe }),
      setDayOverride: (dayOverride) => set({ dayOverride }),
    }),
    { name: 'iris-state' },
  ),
);

/** Apply orb CSS variables based on current vibe + active screen. */
export function applyOrbVibe(vibe: OrbVibe, screenFallback: Exclude<OrbVibe, 'auto'> = 'calm') {
  const effective: Exclude<OrbVibe, 'auto'> = vibe === 'auto' ? screenFallback : vibe;
  const palettes: Record<Exclude<OrbVibe, 'auto'>, [string, string, string, string, string]> = {
    calm: ['#d8efd2', '#a9c8a3', '#6f8c6a', 'rgba(169,200,163,0.35)', '4s'],
    low:  ['#f3d4d4', '#d48a8a', '#a06868', 'rgba(212,138,138,0.40)', '6.5s'],
    high: ['#f4dcb8', '#d4a374', '#a07a55', 'rgba(212,163,116,0.45)', '2.4s'],
    cool: ['#dbe0f0', '#9aa3d4', '#6f78a0', 'rgba(154,163,212,0.35)', '5.5s'],
    dim:  ['#3a3a30', '#2a2a22', '#1a1a14', 'rgba(80,76,64,0.30)',    '7s'],
  };
  const [a, b, c, g, r] = palettes[effective];
  const root = document.documentElement;
  root.style.setProperty('--orb-hue-a', a);
  root.style.setProperty('--orb-hue-b', b);
  root.style.setProperty('--orb-hue-c', c);
  root.style.setProperty('--orb-glow', g);
  root.style.setProperty('--orb-rate', r);
}

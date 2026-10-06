import {
  Activity, ClipboardList, Eye, Gauge, Lightbulb, Mail, Menu, MessageCircle, Network, NotebookPen, Repeat, Scale, Settings, Sun, Upload, Waypoints,
  type LucideIcon,
} from 'lucide-react';
import type { OrbVibe } from '@/hooks/useIrisState';

export interface NavItem { to: string; label: string; icon: LucideIcon; vibe: Exclude<OrbVibe, 'auto'> }
export interface NavGroup { label: string; items: NavItem[] }

/**
 * The app, in four groups by what you are doing: writing, keeping track,
 * understanding what IRIS found, and managing your data.
 */
export const NAV_GROUPS: NavGroup[] = [
  { label: 'Write', items: [
    { to: '/today', label: 'Today', icon: Sun, vibe: 'calm' },
    { to: '/journal', label: 'Journal', icon: NotebookPen, vibe: 'high' },
    { to: '/chat', label: 'Chat', icon: MessageCircle, vibe: 'calm' },
  ] },
  { label: 'Track', items: [
    { to: '/habits', label: 'Habits', icon: Repeat, vibe: 'high' },
    { to: '/decisions', label: 'Decisions', icon: Scale, vibe: 'calm' },
  ] },
  { label: 'Understand', items: [
    { to: '/insights', label: 'Insights', icon: Lightbulb, vibe: 'low' },
    { to: '/patterns', label: 'Patterns', icon: Waypoints, vibe: 'low' },
    { to: '/constructs', label: 'Noticed', icon: Eye, vibe: 'low' },
    { to: '/ideas', label: 'Ideas', icon: Network, vibe: 'cool' },
    { to: '/review', label: 'Review', icon: Mail, vibe: 'cool' },
  ] },
  { label: 'Your data', items: [
    { to: '/questionnaire', label: 'Questionnaire', icon: ClipboardList, vibe: 'calm' },
    { to: '/import', label: 'Import', icon: Upload, vibe: 'cool' },
    { to: '/sensors', label: 'Sensors', icon: Activity, vibe: 'dim' },
    { to: '/observatory', label: 'Observatory', icon: Gauge, vibe: 'dim' },
    { to: '/settings', label: 'Settings', icon: Settings, vibe: 'dim' },
  ] },
];

/** On a phone: the three things done daily, and a menu for the rest. */
export const PHONE_BAR = ['/today', '/journal', '/chat'];
export const MenuIcon = Menu;

export function vibeFor(pathname: string): Exclude<OrbVibe, 'auto'> {
  const first = '/' + (pathname.split('/')[1] || 'today');
  for (const group of NAV_GROUPS) {
    const hit = group.items.find(item => item.to === first);
    if (hit) return hit.vibe;
  }
  return 'calm';
}

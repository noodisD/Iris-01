/**
 * Colours and fonts live in tokens (src/styles/tokens.css), not in screens.
 * A screen that writes a hex colour or a font family drifts from the system.
 *
 * NOT_YET_MIGRATED lists the files still carrying old inline values. It may
 * only shrink: move a file onto the kit, then take it off the list.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

const NOT_YET_MIGRATED = new Set([
  'components/AudioRecorder.tsx',
  'components/IdeaGraph.tsx',
  'components/journal/CheckinPicker.tsx',
  'components/journal/EditorToolbar.tsx',
  'components/journal/MarkdownEditor.tsx',
  'components/journal/MarkdownView.tsx',
  'components/sensors/DayGrounding.tsx',
  'screens/ChatScreen.tsx',
  'screens/ConstructsScreen.tsx',
  'screens/DecisionsScreen.tsx',
  'screens/HabitsScreen.tsx',
  'screens/IdeasScreen.tsx',
  'screens/ImportScreen.tsx',
  'screens/InsightsScreen.tsx',
  'screens/JournalScreen.tsx',
  'screens/OnboardingScreen.tsx',
  'screens/PatternsScreen.tsx',
  'screens/ReviewScreen.tsx',
  'screens/SettingsScreen.tsx',
  'screens/TodayScreen.tsx',
]);

const SRC = join(__dirname, '..');
const DIRS = ['screens', 'components'];

function files(dir: string): string[] {
  return readdirSync(dir).flatMap(name => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

const HEX = /#[0-9a-fA-F]{6}\b/;
const FONT = /fontFamily/;

describe('design tokens guardrail', () => {
  const checked = DIRS.flatMap(dir => files(join(SRC, dir))).map(path => ({
    name: relative(SRC, path), text: readFileSync(path, 'utf8'),
  }));

  it('keeps colours and fonts out of migrated screens and components', () => {
    const offenders = checked
      .filter(f => !NOT_YET_MIGRATED.has(f.name) && (HEX.test(f.text) || FONT.test(f.text)))
      .map(f => f.name);
    expect(offenders).toEqual([]);
  });

  it('lists only files that still need migrating', () => {
    const clean = checked
      .filter(f => NOT_YET_MIGRATED.has(f.name) && !HEX.test(f.text) && !FONT.test(f.text))
      .map(f => f.name);
    expect(clean, 'these are migrated: remove them from NOT_YET_MIGRATED').toEqual([]);
  });
});

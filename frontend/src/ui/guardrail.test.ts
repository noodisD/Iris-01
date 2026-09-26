/**
 * Colours and fonts live in tokens (src/styles/tokens.css), not in screens.
 * A screen that writes a hex colour or a font family drifts from the system.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

// Renderers that take colours as values, not CSS (WebGL): exempt on purpose.
const RENDERERS = new Set(['components/IdeaGraph.tsx']);

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
// A font named directly; `fontFamily: 'var(--font-read)'` is a token and fine.
const FONT = /fontFamily:\s*['"](?!var\()/;

describe('design tokens guardrail', () => {
  const checked = DIRS.flatMap(dir => files(join(SRC, dir))).map(path => ({
    name: relative(SRC, path), text: readFileSync(path, 'utf8'),
  }));

  it('keeps colours and fonts out of screens and components', () => {
    const offenders = checked
      .filter(f => !RENDERERS.has(f.name) && (HEX.test(f.text) || FONT.test(f.text)))
      .map(f => f.name);
    expect(offenders).toEqual([]);
  });
});

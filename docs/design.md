# The IRIS web design system

IRIS is a private instrument for looking at yourself: you write, then you judge
what it found. It has one reader, used every day on a laptop and a phone. The web
app follows one system, "Iris: lens and flower". It is dark only.

- Tokens live in `frontend/src/styles/tokens.css`.
- The component kit lives in `frontend/src/ui/`.
- Each screen styles itself with a CSS Module next to it (`FooScreen.module.css`).

## Principles

1. **Colour carries meaning, never decoration.**
   - Violet (`--iris`) means act or focus.
   - Gold (`--pollen`) means *you confirmed this*: an accepted idea, a verdict, an approved item.
   - Green and rose (`--better`, `--worse`) appear only in data.
   - Nothing else gets colour.
2. **Plain headings.**
   - Titles are in sentence case.
   - No italic accent word.
   - No uppercase or tracked eyebrow label.
   - No "A · B · C" strings; write a sentence or use commas.
   - A line above a title appears only when it carries information, like the date on Today.
3. **Spend the boldness once.** The lens (`<Lens>`), an iris with a pupil, sits in the sidebar and on Today. Everything else stays quiet.
4. **Panels only for things you act on.**
   - Use `<Panel>` for a pattern to judge, an entry, or a batch to review. Everything else is a plain `<Section>`.
   - Radii follow hierarchy: panels 14 px, controls 8 px, pills fully round.
5. **Motion answers actions:** a message arriving, a verdict landing. There are no entrance animations. `prefers-reduced-motion` switches motion off everywhere.
6. **Numbered markers only for real sequences.** A form's questions are not steps.

## Tokens

| Group | Tokens |
|---|---|
| Surfaces | `--night` page, `--deep` navigation, `--dusk` raised, `--dusk-2` raised further or hover, `--mist` borders, `--mist-2` stronger borders |
| Text | `--petal` primary, `--petal-2` secondary, `--petal-3` tertiary. All three meet 4.5:1 on `--night` |
| Meaning | `--iris`, `--iris-text` (violet as text), `--iris-soft`, `--on-iris`, `--pollen`, `--pollen-soft`, `--better`, `--worse`, `--danger` |
| Categorical | `--hue-green`, `--hue-amber`, `--hue-blue`, `--hue-rose`: colours the owner picked, such as a habit's. Never used for meaning |
| Type | `--font-read` (Newsreader) for titles and everything you read or write; `--font-ui` (Schibsted Grotesk) for the interface and numbers. Scale `--text-xs` 12 to `--text-3xl` 39, ratio 1.25. No monospace |
| Space | `--space-1` 4 px to `--space-8` 56 px, `--page-pad` (24 px on phones, 40 px on desktop) |
| Shape | `--radius-panel`, `--radius-control`, `--radius-pill`, `--focus-ring` |
| Measure | `--measure-reading` 720 px, `--measure-standard` 1040 px |
| Lens | `--orb-hue-a/b/c`, `--orb-glow`, `--orb-rate`, set per page by `applyOrbVibe` |

Both fonts are self-hosted through `@fontsource`. No request goes to a font CDN.

## The kit (`@/ui`)

| Component | Use it for |
|---|---|
| `Page` | Every screen's frame: `title`, optional `lead`, `description`, `actions`, `width="reading \| standard \| wide"` |
| `Section` | A titled part of a page, with no box |
| `Panel` | A raised surface for something you act on. `tone="confirmed"` for something the owner confirmed |
| `Button`, `IconButton` | `variant="primary \| secondary \| quiet \| danger"`, `size="md \| sm"`. `IconButton` needs a `label` |
| `ChoiceGroup` | Pick one of a few: verdicts, filters, check-in scores. Uses arrow keys. `tone="confirm"` shows the pick in gold |
| `Tabs`, `TabPanel` | Controlled tabs with arrow keys. Keep the tab in the URL (`?view=` or `?tab=`) |
| `Field` | A visible label, hint and error wired to one control |
| `DataTable` | Tables. Mark numeric columns `numeric` for right-aligned tabular figures; the table scrolls sideways on phones |
| `Badge`, `Stat` | A status word; a number with its label |
| `Sheet` | A focus-trapped side sheet, used by the phone menu |
| `Lens` | The iris motif |

Loading, error and empty states come from `components/states.tsx`.

## Layout

- **Desktop:** a 240 px sidebar in four groups: Write, Track, Understand, Your data. It folds to a 64 px icon rail, and the choice is remembered.
- **Below 768 px:** a bottom bar (Today, Journal, Chat, Menu). Menu opens a sheet with every group.
- **Two-pane screens** (Patterns, Sensors review, Ideas detail) become list-then-detail below 900 px, with a "← All …" button. Decisions stacks its list under the form below 1100 px.
- **Content** is left-aligned. Reading text stays under about 72 characters.

## Rules the tests enforce

`src/ui/guardrail.test.ts` fails if a file in `screens/` or `components/` contains a hex colour or a literal `fontFamily`. Add a token instead.

The one exemption is `components/IdeaGraph.tsx`. WebGL takes colours as values, not CSS.

## Checking a change

```
cd frontend
npx vitest run && npm run lint && npm run build
```

Then take screenshots at 390, 768 and 1440 px and run axe-core on each route. The target is:

- no horizontal scroll at 390 px;
- no serious or critical axe violations;
- a visible focus ring on everything you can reach by keyboard.

Keyframes used inside a CSS Module must be defined in that module, because CSS Modules rename them.

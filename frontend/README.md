# Iris — Frontend

React + TypeScript + Vite, served by the same FastAPI process that stores the
data (`iris_api.py`). Every screen reads the live backend through a typed API
layer; there are no mocks.

## Quick start

```bash
cd frontend
cp .env.example .env.local      # leave VITE_BACKEND_URL empty in development
npm install
npm run dev                     # http://localhost:5173, proxying /api to the backend
```

```bash
npm run build      # type-check + production build (served by iris_api.py)
npm run lint       # tsc --noEmit — noUnusedLocals is on, so dead code fails it
```

## Layout

```
src/
  api/          one file per domain; each function is one HTTP call
    client.ts   fetch wrapper: JSON, one error shape (FastAPI `detail` included), SSE
  hooks/        React Query hooks over api/ — screens use these, never fetch
  screens/      one per route
  components/   shell (Sidebar, AppLayout), loading/error/empty states, primitives
  lib/          dates, query keys
  types/api.ts  the API contract, hand-kept in step with iris_api.py
```

## Screens

| Route          | What it shows |
|----------------|---------------|
| `/chat`        | the conversation; replies stream as the model writes them |
| `/today`       | the featured finding, if any, and today's habits |
| `/journal`     | write an entry; the archive, newest first |
| `/habits`      | today's ticks, as a list or sized by streak |
| `/insights`    | what IRIS noticed — the same admitted list chat draws from — and each finding's evidence; snooze or resolve |
| `/constructs`  | "Noticed": patterns found by reading, with verbatim quotes, waiting to be confirmed |
| `/review`      | the week |
| `/import`      | stage an export, fix dates, commit |
| `/settings`    | what IRIS holds about you, and which engines and confidence it may speak from |
| `/onboarding`  | first run: one paragraph, one button |

## Conventions

- **Tokens, not hex.** CSS vars (`var(--sage)`) or the `color()` helper.
- **Every async screen** handles loading, error and empty via `components/states.tsx`.
- **A failure is shown, never swallowed.** A chat send that fails removes its
  bubbles, reconciles with what the server stored, and says why; a journal save
  that fails keeps the draft and says so.
- **No business logic in components.** Admission, scoring and pattern detection
  happen on the server; the frontend renders what the API returns, and never
  words a finding as a cause or a recommendation.

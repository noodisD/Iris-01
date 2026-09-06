# Iris — Frontend

Production-shaped React + TypeScript + Vite frontend for the Iris wellness companion.
Backend-agnostic: every screen reads through a typed API layer that can run against
your real backend or against in-memory mocks for offline frontend work.

> This `frontend/` app is the engineering scaffold. The hand-built design prototype
> lives at the project root (`index.html` + `screens/*.jsx`) and remains the visual
> source of truth. Where a screen here is marked **PARTIAL PORT**, the richer layout
> exists in the matching prototype file and should be ported over.

---

## Quick start

```bash
cd frontend
cp .env.example .env.local      # then edit values
npm install
npm run dev                     # http://localhost:5173
```

By default `.env.example` sets `VITE_USE_MOCKS=true`, so it runs with no backend.
Flip to `false` and set `VITE_BACKEND_URL` to hit the real API.

```bash
npm run build      # type-check + production build
npm run preview    # serve the build
npm run lint       # tsc --noEmit
```

---

## Architecture

```
src/
  types/api.ts         ← THE CONTRACT. All wire shapes. Mirror this on the backend.
  api/
    client.ts          ← fetch wrapper: auth, JSON, errors, SSE streaming, mock switch
    chat.ts            ← per-domain calls (chat, habits, insights, body, journal, …)
    habits.ts            each function checks useMocks() and dispatches to lib/mock
    insights.ts          or the real endpoint.
    body.ts
    journal.ts
    settings.ts
    review.ts
    onboarding.ts
  hooks/
    useChat.ts         ← Tanstack Query hooks + optimistic mutations + SSE wiring
    useHabits.ts       ← optimistic habit toggle
    useInsights.ts
    useData.ts         ← simple read hooks (body, review, journal, user, …)
    useIrisState.ts    ← Zustand store: orb vibe + day override, persisted
  components/
    AppLayout.tsx      ← sidebar + <Outlet/>
    Sidebar.tsx        ← nav + orb (drives orb hue per route)
    primitives.tsx     ← Sparkline / BarSeries / Ring / Orb / Tag / color()
    states.tsx         ← Loading / Error / Empty / Skeleton
  screens/             ← one file per route; reads hooks, renders
  lib/
    queryClient.ts     ← QueryClient + query-key registry (qk)
    mock.ts            ← in-memory fixtures (faithful to types/api.ts)
  styles/tokens.css    ← design tokens + base classes (ported from prototype)
  App.tsx              ← router
  main.tsx             ← entry: QueryClientProvider + StrictMode
```

### Data flow

```
Screen → hook (useXxx) → api/xxx.ts → client.ts → fetch /api/...   (real)
                                    ↘ lib/mock.ts                   (VITE_USE_MOCKS=true)
```

Screens never call `fetch` directly and never import mocks directly. They use hooks.
Hooks own caching, loading/error state, and optimistic updates.

---

## Wiring your backend

1. **Implement the endpoints** listed at the top of each `src/api/*.ts` file. The
   suggested REST shape is documented there; adjust paths to taste and update the
   api module — screens won't change.

2. **Match the types** in `src/types/api.ts`. If you generate types from a schema
   (OpenAPI / protobuf / zod), make this file the generated output or assert against it.

3. **Auth.** `client.ts` sends `credentials: 'include'`. Add bearer/CSRF headers there
   if you use them. The Vite dev proxy (`vite.config.ts`) forwards `/api/*` to
   `VITE_BACKEND_URL` so cookies work in dev.

4. **Chat streaming.** `api/chat.ts#streamReply` consumes Server-Sent Events from
   `POST /api/conversations/:id/messages/stream`. Emit `data: {"text":"…"}` chunks
   and a final `data: {"done":true,"messageId":"…"}`. If you prefer WebSocket, swap
   the body of `streamReply` — the hook (`useChat.ts`) is transport-agnostic.

5. **Flip `VITE_USE_MOCKS=false`** and delete `lib/mock.ts` imports once everything’s live
   (or keep them — they're tree-shaken out when mocks are off, and useful for tests).

---

## Screen status

| Route          | Screen file            | Status        | Notes |
|----------------|------------------------|---------------|-------|
| `/chat`        | ChatScreen.tsx         | **Complete**  | streaming reply, quick replies, inferred rail |
| `/habits`      | HabitsScreen.tsx       | **Complete**  | optimistic toggle, list + constellation |
| `/insights`    | InsightsScreen.tsx     | **Complete**  | index + deep-dive (twin-series, quotes, suggestions) |
| `/review`      | ReviewScreen.tsx       | **Complete**  | cinematic letter + word-poem |
| `/journal`     | JournalScreen.tsx      | **Complete**  | composer + recent + recurring phrases |
| `/settings`    | SettingsScreen.tsx     | **Complete**  | knowledge facts + connector toggles |
| `/body`        | BodyScreen.tsx         | Partial       | port hypnogram + HRV↔anxiety fusion chart |
| `/today`       | TodayScreen.tsx        | Partial       | port remaining ~9 dashboard cards |
| `/mobile`      | MobileScreen.tsx       | Partial       | mobile preview is a separate RN target |
| `/onboarding`  | OnboardingScreen.tsx   | Partial       | port branching chat → api/onboarding.ts |

"Partial" screens are wired to real hooks and render real data — they're just missing
some of the richer visualizations that exist in the root prototype.

---

## Conventions

- **Tokens, not hex.** Use CSS vars (`var(--sage)`) or the `color()` helper. The orb
  hue is driven by CSS vars set in `Sidebar.tsx` per route.
- **Every async screen** handles loading / error / empty via `components/states.tsx`.
- **Mutations are optimistic** where the user expects instant feedback (habit toggle,
  sending a message) and roll back on error.
- **No business logic in components.** Inference, scoring, and pattern detection are
  the backend's job — the frontend only renders what the API returns. (The mock
  `fakeIrisReply` exists *only* so the chat demos without a backend; delete when live.)

---

## What's deliberately NOT here

- Auth screens (login/signup) — add under a `/auth` route group.
- Real mobile app — separate React Native / native target.
- On-device ML / wearable SDK integration — backend + native concern.
- Tests — add Vitest + Testing Library; the hook/api split makes screens easy to test
  with a mocked query client.

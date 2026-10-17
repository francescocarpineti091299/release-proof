# ReleaseProof web UI (WS-F)

Next.js 16 (App Router), React 19, TypeScript strict, Tailwind 4. English, API-driven, no per-run hardcoded text.

## Run

```powershell
npm install

# Real API: next dev proxies /api/* to API_ORIGIN (default http://localhost:8000)
$env:API_ORIGIN='http://localhost:8000'; npm run dev

npm run lint
npm run typecheck
npm test                                       # Node 22.6+, no backend required
npm run build
npm run test:smoke                              # owns a temporary standalone server
npm audit --omit=dev
docker build -t releaseproof/web .              # standalone, port 3000, non-root
```

The UI requires a running backend; it always uses the real API and has no in-browser mock mode. Backend test doubles remain separate from the frontend. The Reference run is recorded historical evidence, clearly labelled as such, not a new execution.

In production, Caddy routes `/api/*` to the API and everything else to `web:3000` (same origin). The browser makes every call client-side.

## Pages

| Route | Content |
|---|---|
| `/` | Hero, 3-step wizard (configuration → change → planned checks → Run), recent runs, RECORDED reference card |
| `/runs/[runId]` | Live stage timeline, queue position, tests, AI plan, log tail (SSE), decision (migration / candidate / transition), main causes with citations, verified / unknown, AI alternatives with "Evaluate this plan", evidence explorer, requirement/invariant table, AMD traces, technical details + dossier, assistant drawer |
| `/reference` | Recorded WP0 freeze (`GET /api/reference`) under a persistent RECORDED banner |
| `/amd` | Provider, hardware, models per module, call count, OK rate, p50/p95, tokens, recent traces |

## Code map

- `lib/types.ts`: hand-written mirrors of `contracts/{runner,api,ai,profile}.py` (exact field names).
- `lib/api.ts`: real API client + SSE (`EventSource`, all 9 event types, envelope or bare payloads, reconnect with `Last-Event-ID`).
- `lib/run-events.ts`: envelope/bare event parsing and safe integer resume cursors.
- `lib/assistant-stream.ts`: plain-text/SSE assistant decoding (fragmented UTF-8, CRLF, final frame, cancellation and bounded SSE frames).
- `lib/safe-url.ts`: artifact navigation allows root-relative paths and HTTP(S), rejects active schemes and protocol-relative URLs.
- `lib/semantics.ts`: verdict wording and colours, stage labels, deterministic causes/unknowns derived from the V1.2 result.
- `components/run/use-live-run.ts`: live state (REST snapshot + SSE patches + polling fallback).

## API used (aligned with the running backend, WS-C)

`GET /api/configurations` (ConfigurationView: changes → templates[required], alternatives, est_seconds_total) ·
`GET /api/catalog/tests` · `GET|POST /api/assessments` (`Idempotency-Key` header + body key) · `GET /api/assessments/{id}` ·
`/plan` · `/result` (404 until ready) · `/artifacts` (+ `/artifacts/{artifact_id}` download) · `/ai-traces` ·
`/events` (SSE envelope `{id,type,data}`, resume with `Last-Event-ID` or `?after=`) ·
`POST /api/assessments/{id}/alternatives/{plan_id}/evaluate` (`Idempotency-Key`) · `POST /api/assistant` (text/plain stream) ·
`GET /api/reference` (`{recorded, recorded_at, notice, canonical_hash, run, result}`) · `GET /api/amd` (`{provider, traces}` aggregates;
recent traces are collected client-side from `/ai-traces` of the latest runs).

`next.config.ts` sets `compress: false`: Next's gzip buffers proxied `text/event-stream`, which would freeze the live log in dev.

## Frontend assurance and limitations

Next.js is pinned to 16.4.2 (including the matching ESLint config), React to 19.2.9. Keep lockfiles in sync with these versions; previous Next 16.0.x versions had critical published advisories, including Windows-hosted RCE.

`npm test` uses Node's native runner with experimental TypeScript stripping, without additional test dependencies or frontend mocks. It covers stream chunk boundaries, CRLF, EOF, Unicode, callback errors, oversized SSE frames, artifact URL schemes and live-event cursors. `npm run test:smoke` (after build) owns a temporary standalone server on a free port and checks six server-rendered pages, including literal percent signs in run IDs; it never starts backend runs or attaches to an existing dev server. Node 22 may print experimental/module-detection warnings; these are unrelated to ESLint warnings.

Live views retry when the initial REST load fails, subscribe after recovery, ignore late responses from disposed effects, deduplicate resumed event IDs and give terminal replay time to deliver stored logs. UI replay still has an 8-second time budget: exceptionally large/slow stored streams can be incomplete. The displayed log tail is capped at 2,000 lines and stream errors at 100; download artifacts for the complete record.

Run path parameters are already decoded by App Router and are not decoded a second time. Assistant histories are scoped to each run; cancelled/empty replies do not leave a permanent loading placeholder. Raw HTML is not enabled in Markdown, and artifact URLs from API payloads cannot activate `javascript:`, `data:` or `file:` schemes.

This is not an authentication or authorization boundary. Deploy behind access controls/rate limits appropriate to the backend and AI costs. Network integration with the real runner/AMD endpoint and browser-level focus/layout/accessibility testing are separate from these unit tests and production builds; they require a running backend and browser tooling.

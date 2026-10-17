# ReleaseProof web UI (WS-F)

Next.js 16 (App Router), React 19, TypeScript strict, Tailwind 4. English, API-driven, no per-run hardcoded text.

## Run

```powershell
npm install

# Mock mode: no backend. Realistic fixtures, a live wolfBoot run streams over ~20 s.
$env:NEXT_PUBLIC_MOCK='1'; npm run dev          # http://localhost:3000

# Real API: next dev proxies /api/* to API_ORIGIN (default http://localhost:8000)
$env:API_ORIGIN='http://localhost:8000'; npm run dev

npm run lint; npm run build                     # both must pass
docker build -t releaseproof/web .              # standalone, port 3000, non-root
docker build --build-arg NEXT_PUBLIC_MOCK=1 -t releaseproof/web:mock .   # demo image without backend
```

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
- `lib/api.ts`: typed client + SSE (`EventSource`, all 9 event types, envelope or bare payloads, reconnect with `Last-Event-ID`). Switches to `lib/mock/client.ts` when `NEXT_PUBLIC_MOCK=1`.
- `lib/semantics.ts`: verdict wording and colours, stage labels, deterministic causes/unknowns derived from the V1.2 result.
- `lib/mock/`: profiles + catalog, scenarios, a time-driven simulator (`sim.ts`), and `data/*.json` (real engine output for the WP0 baseline and the conditional scenario).
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

# Code review and hardening — 2026-10-17

## Scope and boundaries

Reviewed ReleaseProof's deterministic core, adapters, API, orchestrator, store, AMD gateway,
frontend, common/wolfBoot/MCUboot runners, scripts and deployment documentation. The companion
`firmware-migration-assurance` POC was reviewed separately; in the sibling repository its findings
are documented in `firmware-migration-assurance/docs/CORE_HARDENING.md` (workspace-relative path).

Pre-existing local mock-removal changes were retained. No history was reset, reference facts
were rewritten, normative V1.1/V1.2 packs were changed, or profiles were promoted by this review.
The already-running Compose stack was not rebuilt/restarted. Tests do not prove that this
existing deployment is running the reviewed source.

## Corrections

### Deterministic core

- Validation is fail-closed for malformed data, missing schemas, duplicate IDs, orphan references
  and authorization changes whose individual path is not covered by a transition effect.
- `allowed_actions` is enforced as well as component allow-lists.
- Only evidence with `status=VALID` may satisfy evaluation predicates. That status is input
  metadata, not proof of cryptographic authenticity or independent human review.
- Invalid/missing layout dimensions remain UNKNOWN. Boolean/float/coerced dimensions and
  irrelevant artifacts no longer produce spurious fit verdicts. Contradictory observations
  are reduced conservatively rather than depending on their order.
- I3 evaluates all authorization paths; trust-chain size checks do not invent zero-byte values
  or special-case scenario evidence IDs as real measurements.
- A4 projection updates references when its final state is renamed.
- Result JSON includes the assurance aliases that were already part of its canonical hash.
  Exported results can now be rehashed directly; frozen golden hashes remain unchanged.

### Backend and wire boundaries

- Artifact owners and paths must resolve inside the run store. Dot paths, colon-bearing path
  segments, invalid artifact URL IDs and the reserved runner ID `MANIFEST` are refused.
- Artifact downloads recheck digest and byte length, including manifests. Changed content
  returns HTTP 409 instead of being served with stale integrity metadata.
- Malformed AI responses, truncated streams, invalid usage values and non-finite timeout
  settings no longer escape as unclassified errors. Streams require the terminal `[DONE]` marker.
- Endpoint URLs cannot contain userinfo, query/fragment or invalid ports; failures do not disclose
  embedded credentials.
- Enqueue order and database insertion are serialized; stopping workers cannot claim new work.
- API shutdown drains active runner/AI operations before closing SQLite, without blocking the
  event loop. An explicit shutdown timeout uses one overall budget and leaves the store open
  if drain is incomplete rather than closing it under a live worker.
- SSE cursors are bounded to SQLite's non-negative signed 64-bit range; invalid `after` is 422.

### Verification/deployment tooling

- Acceptance uses fresh idempotency keys, checks every required public catalog template,
  rejects malformed hashes/empty results, refuses unknown profile selections and retains a
  failed report when one profile's API fails instead of abandoning the remaining checks.
- The manifest digest must match its published artifact, whose downloaded bytes are checked
  even when it falls outside the ordinary artifact sample.
- Benchmark iterations must be positive. Exit status is nonzero for failed logical calls,
  detected injection leaks or verdict-falsification obedience.
- Smoke/benchmark assistant calls recognize interrupted streams after partial text as failures,
  not successful logical calls.
- AWS state values are shell-escaped, so paths containing spaces/apostrophes survive sourcing.
  Teardown preserves state on permission/API errors and tolerates specifically missing resources
  on retry. Deployment health URLs preserve non-default HTTP ports.
- The MCUboot LMS alternative title is quoted in YAML to retain `PR #2707` instead of treating
  the issue number as a comment.

Frontend and runner details are also recorded in their respective READMEs and regression suites.

## Verification

Reproducible offline commands (use the installed backend environment):

```bash
cd backend
python -m pytest
python -m ruff check releaseproof tests
cd ..
python -m pytest scripts/tests -q
PYTHONPATH=runners/common:runners/wolfboot:runners/mcuboot python -m pytest runners -q
cd web
npm run lint
npm run typecheck
npm test
npm run build
```

PowerShell uses `;` in `PYTHONPATH`. Runner-specific Linux/build/emulation checks require the
pinned container toolchains; standalone subprocess tests may skip when platform features are
unavailable. Deployment regressions replace AWS/SSH/curl with local test functions: they do not
provision, terminate or contact cloud resources. AMD script tests inject test responses or omit
credentials and do not make paid inference calls.

The updated pitch PDF was regenerated from `pitch/slides.html`; its ten pages were checked for
the current Token Factory status. Historical screenshot assets were not relabelled as new runs.

Verified results for the reviewed source:

| Suite/check | Result |
| --- | --- |
| Full backend pytest | 378 passed, 1 Windows symlink skip |
| Standalone scripts/deployment regressions | 21 passed |
| Runner tests, Windows | 25 passed, 2 platform-specific skips |
| Runner tests, Linux Docker, read-only sources/no network | 27 passed |
| ReleaseProof web tests | 8 passed |
| Companion POC web tests | 9 passed |
| Companion POC core + WP0 regressions | 178 passed (163 core, 15 standalone WP0) |
| Companion POC verify/export gate | OK; frontend catalog regenerated, golden hashes unchanged |
| Both web workspaces | lint, typecheck, production build, standalone HTTP smoke OK |
| Both web runtime dependency audits | zero reported vulnerabilities |
| Backend/scripts Ruff and Compose config validation | OK |

## Remaining limitations and compatibility decisions

- Run one API worker/replica per data volume. Slot coordination and restart recovery are not
  distributed; adding workers can corrupt job ownership semantics.
- Default graceful shutdown can wait as long as active operations take. A hung worker can keep
  drain pending; forcibly killing the process/container interrupts the run instead of completing
  it. Wait for active runs before deployment/restart, or deliberately accept interrupted runs.
- Authentication, tenant isolation, submission quotas and AI/SSE rate limiting are not built in.
  Subsequent judging policy intentionally permits anonymous HTTPS with bounded jobs/POST requests.
  Stronger identities/isolation remain necessary for customer hosting. Completed-run bookkeeping
  and long-lived connections still need capacity controls for sustained production use.
- Artifact verification and response streaming are not atomic against a hostile concurrent
  filesystem writer. Keep the shared volume trusted and immutable after publication.
- Canonical hashes establish deterministic document identity, not signature authenticity,
  trustworthy acquisition, hardware identity or certification. Reference projection metadata
  `content_hash` for loaded JSON manifests is a JCS-document hash, not necessarily the hash of
  the original pretty-printed bytes. This legacy freeze behavior was not changed; live artifact
  digests and `manifest_sha256` use bytes. Do not conflate those fields.
- Generic V1.2 evidence matching is not a complete requirement-/subject-scoped proof system;
  recorded snapshots and source pins remain declarations until independently verified.
- Renode flash/power-loss modeling and runtime RAM remain limited. Interrupted-update recovery
  stays UNKNOWN; this review does not supply missing E12 hardware evidence.
- No new rebuilt-container live acceptance, cloud deployment, paid AMD smoke or full benchmark
  was performed. Existing acceptance and smoke JSON remain historical records. Managed GPU
  labels are operator declarations. That review did not attest an AWS deployment. Subsequent
  actual cloud checks, cleanup and deployed-runtime drift are recorded separately in
  [`INFRA_AUDIT_2026-10-17.md`](INFRA_AUDIT_2026-10-17.md); they do not retroactively expand this review.

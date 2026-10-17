# Mock and synthetic-data audit

## Scope and approach

Reviewed the frontend API client and reporting paths, backend routes/dependency wiring, live
adapters and verdict engine, shared runner protocol, wolfBoot/MCUboot build and emulation paths,
AMD smoke/benchmark scripts, test helpers, and Docker packaging.

The goal is to exclude synthetic execution paths from the shipped product without deleting
test coverage or misrepresenting emulation as physical hardware validation. This audit does not
attest a deployed instance, authenticate remote runner measurements, or replace end-to-end
acceptance on rebuilt runner containers.

## Changes

| Finding | Action |
| --- | --- |
| Complete in-browser mock API, simulated timelines, AI traces, artifacts and pseudo-hashes | Removed `web/lib/mock/`, the API selector, banner, build flag and mock-specific instructions. The frontend always calls the backend. |
| Test-only AMD endpoint shipped as `releaseproof.ai.stub` | Moved to `backend/tests/ai/rp_llm_stub.py`; preserved adversarial, schema/error and environment-guard tests. |
| Demo assessment generators shipped in `core/projection/scenarios.py`, including simulated E12 closure and policy/recovery declarations | Moved to `backend/tests/unit/rp_scenarios.py`; removed demo catalog exports from the runtime projection package. Engine and planner tests still exercise these fixtures. |
| Standalone HTTP fake runner usable as a runner URL | Removed unused `backend/tests/orchestrator/fake_runner_server.py`. In-process runner fakes remain in tests. |
| Custom adapter/AI factories, evidence indexers or runner transports could be injected into a non-test orchestrator | Added a startup check in `Deps.check_environment`, called by `Orchestrator`. Injection requires `Settings.env == "test"`. |
| Hardware metadata can be mistaken for measured GPU identity | Retained the existing undisclosed-GPU default and added a regression test. README now describes hardware labels as declarations, not attestation. |

Neither setuptools package discovery (`releaseproof*`) nor the API Dockerfile includes
`backend/tests/`. The moved helpers are therefore not included in normal runtime packaging.

## Useful fixtures and models retained

- **Unit/API/orchestrator fakes:** isolate transport failures, queue/restart behavior, AI
  guardrails and verdict independence. They are test inputs, not acceptance evidence.
- **Recorded runner streams:** regression fixtures under `backend/tests/fixtures/runner_streams/`.
  The application does not replay these as live executions.
- **Reference run:** `orchestrator/reference.py` evaluates the recorded WP0 snapshot, exposes
  `mode=REFERENCE` and marks execution stages as skipped. Live-run failures do not fall back
  to this snapshot.
- **A4 projections:** `core/projection/wp0.py` also projects recorded signer refusal and
  artifact-size what-if cases. The latter requires a recorded artifact measurement when no
  explicit measurement is supplied. These are not live-run result generators.
- **MCUboot demo firmware:** a real compiled application that reads its version and key hash
  from the booted image header/TLV area; its UART marker is not a canned success response.
- **NVMC model:** required to execute the Zephyr flash driver in Renode. READY/READYNEXT are
  always true and erase operations complete immediately. Write-enable enforcement, 1-to-0
  programming restrictions and power-loss physics are not modeled. Retained as a documented
  emulation limitation, not hardware proof.
- **UNKNOWN rows and gaps:** E12 interruption/recovery and runtime RAM are not measured by the
  current catalog. Placeholder rows prevent missing observations from silently satisfying
  requirements; they must not be removed or turned into PASS.
- **Alternative-plan recovery declarations:** field-service/depot recovery is a plan declaration,
  explicitly marked `DECLARED`/`UNREVIEWED`, not a measured technician procedure. Re-evaluations
  use parent evidence and do not claim another build/emulation execution.
- **Deterministic planner fallback:** required and optional catalog tests run when AI is
  unavailable. This executes actual test templates; it does not synthesize AI responses or results.
- **AMD benchmarks:** real endpoint calls with recorded assessments and deliberate adversarial
  inputs. They measure AI behavior, not a new firmware migration run. No stub fallback is used.

## Regression coverage and verification

`backend/tests/unit/test_runtime_boundaries.py` checks that removed synthetic modules and
demo exports are unavailable in the runtime package, application source does not import the
test helpers, custom dependency injection is rejected outside test mode, and defaults remain
usable without mock transports. Existing tests verify that runner failures yield no verdict,
AI outages yield no synthetic response, reference evidence is labelled, and missing facts stay
UNKNOWN.

Offline backend/runner tests and frontend lint/typecheck/production build are the validation
scope for this change. A new Docker/Renode end-to-end run and paid AMD endpoint calls are not
performed by the audit. Existing deployments must be rebuilt to apply the cleanup; previously
stored data is not deleted or reclassified.

# ReleaseProof — remediation and hackathon alignment

This follows `COMPLIANCE_AUDIT_2026-10-17.md`; the original findings and historical evidence
are retained. It is not a declaration that external submission/rights steps have been completed.

**Deployment scope:** the controls/live rebuilds below refer to the remediation test stack,
not the existing AWS images. The independently checked cloud demo still has anonymous access,
no new API budget limiter and root/full-volume runners. See
[`INFRA_AUDIT_2026-10-17.md`](INFRA_AUDIT_2026-10-17.md) before claiming these controls on AWS.

## Necessary fixes implemented

| Finding | Change | Proof/remaining boundary |
|---|---|---|
| F01 Signer failure → false incompatibility | Only imgtool exit 2 with explicit invalid `--type` diagnostic is unsupported. Timeout/crash/missing output is ERROR, without decisive crypto evidence. | Adversarial keygen/sign tests; genuine upstream refusal preserved |
| F02 Unchecked assistant stream | Buffer until `[DONE]`, bound output, validate cited IDs and phase-specific verdict words before emitting any generated text; reject certification claims. | Injection/citation/phase-swap regressions; ID validation is not a formal entailment proof |
| F03 Runner root/DB access | Both images use UID 10001; drop all capabilities; mount only `runs/` volume subpath. | Live UID 10001, database invisible in both runners, network `internal=true` |
| F04 Different implementation behind same tag | New manifests include backend/core/adapters and runner code/assets content fingerprints. Result payload rehash is checked; old results unchanged. | Rebuilt API/web/runner images; source match is a release gate, not an assumption from image tags |
| F05 Weak AI acceptance | Require planner trace tied to run/accepted plan and approved host, actual selected plan execution, validated explanation/alternatives; rehash every artifact/result/manifest. | Explainer/alternatives-only trace regression now fails |
| F06/07 Submission packaging | Compact title/short/long form copy, selected-track tags only, machine-readable final fields and fail-closed checker. | 42 / 221 / 1,728 characters; real URLs/team/uploads still operator steps |
| F08 Inventory/provenance | Runtime Python + production npm inventory (188 records), exact versions/license metadata/integrity, limitations, updated provenance. | Not an OS/toolchain-complete SBOM; author/organizer rights confirmation cannot be inferred |
| F09 Public access/consumption | The owner superseded the earlier login gateway: public judging is anonymous, with HTTPS and bounded API jobs/POST requests. | Public override/deploy now require anonymous HTTP 200, not 401; no tenant/customer-data isolation claim. Earlier authenticated gateway checks are historical, not the current judging policy. |
| F10 Missing audit links | Existing `docs/CODE_AUDIT.md` is now present from the preceding hardening work; README links resolve. | Keep that earlier review distinct from this remediation and new live tests |

### Non-root integration correction

The first rebuilt acceptance caught an inherited MCUboot warmup key left at a fixed root-owned
`/tmp` location. Keys now remain in the disposable per-run workspace and are removed with it.
Workspace failures are cached, preventing a retry from masking the original error with a partial
source-copy collision. Both a real failed-run report and a regression test are retained.
The non-root image now provides an explicit writable HOME/XDG cache and preconfigures west's
local `zephyr.base`; it does not allow west/CMake to mutate root-owned checkout metadata.
The image's complete MCUboot warmup/self-test runs **after USER rp**, so permission regressions
fail the image build rather than being hidden by a root-only warmup.

Runner fingerprints sort relative POSIX path strings explicitly, so Windows/Linux do not
disagree merely because `CMakeLists.txt` sorts differently under their path comparison rules.

## Deliberate choices retained (not defects)

- AMD Token Factory instead of operating a dedicated MI300X/vLLM deployment: expressly offered
  by the event and already integrated. No unsupported GPU identity is claimed.
- Same nRF52840 board with wolfBoot and MCUboot: two genuinely different configurations,
  explicitly permitted by the engineering brief. No second physical board is fabricated.
- SQLite/single API worker and bounded process-local queue: appropriate for this demo;
  replacing it with a distributed platform would not improve this submission's correctness.
- Deterministic non-generative fallback on AMD outage: preserves real measurements. It does
  **not** pass the stricter AI submission gate or claim an AI planner was executed.
- E12 and runtime RAM remain UNKNOWN. A migration INCOMPATIBLE is a valid measured outcome,
  not a reason to adjust evidence or golden tests until the result becomes positive.
- Runners still share a trusted artifact namespace. Mount isolation keeps DB out of reach,
  but these are controlled open-source fixtures, not an arbitrary hostile-firmware upload
  service. Per-tenant volumes, immutable object storage and deep sandboxing remain production
  work, not falsely completed hackathon features.
- A small real AMD benchmark is labelled with its actual sample size; smoke counts are not
  substituted for statistical reliability or a measured engineering-hours/ROI saving.

## Verification commands

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
cd ..
$env:PYTHONPATH='runners/common;runners/wolfboot;runners/mcuboot'
.\backend\.venv\Scripts\python.exe -m pytest runners/common/tests runners/wolfboot/tests runners/mcuboot/tests scripts/tests -q
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
.\backend\.venv\Scripts\python.exe scripts/acceptance.py --base http://localhost:8080 --require-ai --env-file .env
.\backend\.venv\Scripts\python.exe scripts/amd_benchmark.py --env-file .env -n 1
.\backend\.venv\Scripts\python.exe scripts/dependency_inventory.py
```

Frontend lint/typecheck/eight tests pass; production Turbopack build and standalone packaging
were verified by the rebuilt Docker image, not by deleting a user's local Next lock.

Latest frozen-source offline verification (including independently added evidence-pack/release
gate work, preserved and integrated): **420 backend passed, 1 skipped; 53 script tests passed;
38 runner tests passed, 2 platform skips**. Backend Ruff and frontend lint/typecheck pass.
Public-gateway regression used separate temporary credentials/container, not real judge secrets.

The real AMD sample (`docs/AMD_BENCHMARK.json`, one iteration, seven logical calls) recorded
three OK calls, three upstream timeout failures and one withheld assistant response. Schema
validity among reached structured replies was 1.0, but citation/verdict rates were **not
measurable** because explainers failed upstream. The injection case timed out: zero observed
leaks is not a successful injection-resistance test. The earlier independently added sample
was preserved as `AMD_BENCHMARK_PRIOR_20261017T133903Z.json`. Do not substitute either report
for proof of the current frozen deploy or claim complete provider reliability.

### Final rebuilt live verification

`docs/RELEASE_EVIDENCE.json` independently confirms that the running backend and both runners
match the local source fingerprints. Both runner images build as non-root; MCUboot's complete
build/sign/emulation self-test runs as that same user. wolfBoot's image also checks imports
using its actual Python 3.10; its/shared Ruff targets prevent an unsafe datetime.UTC upgrade.

The final fresh strict report is `docs/acceptance/20261017T150911Z.json`:

- MCUboot run `RP-20261017T145747Z-946222`: pipeline SUCCEEDED, 6/6 required/planned tests,
  positive boot and two negative controls, 45 artifacts fully hash-verified; source matches,
  canonical result rehash and AMD planner/plan execution pass. **AMD explainer timed out;
  alternatives failed with an upstream 500/504 timeout.** These steps remain AI_UNAVAILABLE.
- wolfBoot run `RP-20261017T150425Z-e0538f`: pipeline SUCCEEDED, 7/7 tests, positive/negative
  controls, 57 fully hash-verified artifacts; all source/hash and planner/report/alternatives
  gates pass. Candidate COMPATIBLE, transition/migration INCOMPATIBLE remains correct.

Thus the firmware pipelines and implemented safety fixes are verified, but the **complete AMD
demo gate is still FAILED for MCUboot**. This is retained honestly, not relabelled as success.
Retry that profile when the managed service is available before final demo capture; do not
weaken the gate, substitute old outputs, or treat a timed-out adversarial case as a success.

A genuine guardrail false positive was also removed: lower-case "PQC-compatible bootloader"
is a capability adjective, not a migration verdict. Alternatives still reject uppercase verdict
labels and explicit phase/plan verdict assertions; they retain allowed-plan/external-validation
constraints. Separate tests cover both accepted descriptive language and rejected verdict claims.

## Final external gate

See `HACKATHON_READINESS.md` and fill `pitch/submission_fields.json`. Final URLs, owner/team,
registration, rights/prior-work approval, external judge walkthrough, authentic video/PDF and
successful platform submission cannot be completed by editing source code or by checking
`SUPPORTED=true`. `scripts/submission_check.py` deliberately fails until actual confirmations
and fresh strict acceptance evidence are supplied.

Owner/team/registration/rights confirmations are now recorded in `pitch/submission_fields.json`;
the supplied public MIT repository and existing CloudFront URL were opened independently.
The video is explicitly still to be made. The public repository/demo must receive the reviewed
final changes; their availability alone does not show that this hardened local source is published.

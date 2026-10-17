# Code provenance

ReleaseProof was built during the AMD Developer Hackathon ACT III (12–18 Oct 2026) on top of a
private proof of concept owned by the same author.

| Area | Origin | Notes |
|---|---|---|
| `contract/PQC_Engineering_Pack_V1_2/` | **Pre-existing** (POC `firmware-migration-assurance`, frozen 2026-10-01) | Copied verbatim. Normative semantic contract, schemas, golden hashes. |
| `backend/releaseproof/core/` | **Pre-existing**, ported | Semantic engine (`validate_assessment`, `evaluate`, canonical hash, explanation graph). Imports/paths adapted. One additive change (decision D05: evidence selection by `test_id`), golden hashes unchanged. |
| `backend/tests/unit/` (ported files) | **Pre-existing**, ported | SV01–SV15, golden, verdict precedence, hash vectors. |
| `reference/wp0-freeze-20261001/` | **Pre-existing** run records | Manifests/logs of the recorded WP0 freeze. Shown in the UI only as a *recorded reference*, never as a live run. |
| `runners/wolfboot/` | **New**, informed by the POC `wp0/harness` | Re-implemented as an isolated, job-scoped runner. |
| Everything else (`backend/releaseproof/{contracts,profiles,orchestrator,api,store,ai,adapters}`, `runners/mcuboot`, `web/`, `deploy/`, `scripts/`, `docs/`) | **New during the hackathon** | |

Third-party source (wolfBoot, wolfSSL, Zephyr, MCUboot, Renode) is **not** vendored in this
repository: runner images fetch it at pinned commits at build time. See `THIRD_PARTY_NOTICES.md`.

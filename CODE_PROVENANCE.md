# Code provenance

ReleaseProof was built during the AMD Developer Hackathon ACT III (12–18 Oct 2026). It builds on a
private proof of concept by the same author.

| Area | Origin | Notes |
|---|---|---|
| `contract/PQC_Engineering_Pack_V1_2/` | **Pre-existing** (POC `firmware-migration-assurance`, frozen 2026-10-01) | Copied verbatim: the normative semantic contract, schemas and golden hashes. |
| `backend/releaseproof/core/` | **Pre-existing**, ported and hardened | Semantic engine (`validate_assessment`, `evaluate`, canonical hash, explanation graph). Imports and paths were adapted; D05 adds evidence selection by `test_id`. Validation, evidence-boundary and result-serialization fixes were added during the event. The frozen golden hashes are unchanged. |
| `backend/tests/unit/` (ported files) | **Pre-existing**, ported | SV01–SV15, golden vectors, verdict precedence, hash vectors. |
| `reference/wp0-freeze-20261001/` | **Pre-existing** run records | Manifests and logs of the recorded WP0 freeze. Shown in the UI only as a labelled *Reference run*, never as a live run. |
| `runners/wolfboot/` | **New**, informed by the POC harness | Re-implemented as an isolated, job-scoped runner. |
| Everything else: `backend/releaseproof/{contracts,profiles,orchestrator,api,store,ai,adapters}`, `runners/mcuboot`, `runners/common`, `web/`, `deploy/`, `scripts/`, `docs/` | **New during the hackathon** | |

Built during the event:

- the AMD AI gateway and its guardrails;
- the orchestrator and the live UI;
- both runners and the MCUboot NVMC flash model;
- evidence packs and the release gate;
- signer-error classification;
- non-root runner isolation;
- bounded public-demo budgets;
- source fingerprints and the strict acceptance gate.

Third-party source (wolfBoot, wolfSSL, Zephyr, MCUboot, Renode) is **not** vendored in this
repository. The runner images fetch it at pinned commits at build time. See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

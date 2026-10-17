# AMD ACT III — release and submission gate

This checklist separates official event rules from the project's stricter engineering brief.
**No script can certify account enrollment, IP ownership or organizer acceptance.**

## Official requirements and scope

- Track: **Intelligent Industry**. Target users: industrial/IoT firmware and product-security teams.
- A meaningful AMD workload must be in the working product. AMD Token Factory is explicitly
  offered by the event; managed inference is sufficient as a technology choice. Specific
  MI300X/ROCm/vLLM or EC2 deployment claims need evidence and are not made by default.
- Google/Gemma and Evolus are optional partner awards, **not** requirements for this track.
  The project also targets the **Google/Gemma award**: all LLM modules default to
  `Gemma-4-31B-IT`, served on AMD Token Factory.
- Public authorized GitHub repository; working app URL; title, short/long descriptions,
  technology tags, cover, video and PDF pitch presentation.
- Standard form limits: title 5–50, short 50–255, long 600–2,000 characters. MP4/MOV video
  up to 300 MB; under five minutes is recommended. The ACT III authenticated form overrides
  generic limits. `pitch/submission.md` now has compact form copy.
- Team 1–6; lablab/Discord and AMD Developer Program enrollment. Check the authenticated form.
- Rome Luma deadline: **18 October 2026, 16:00 Europe/Rome**, unless organizers update it.

Sources (checked 17 October):
[Event](https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-iii),
[Rules](https://lablab.ai/hackathon-rules),
[Submission](https://lablab.ai/delivering-your-hackathon-solution),
[Rome](https://luma.com/AMDHackathon-Rome).

## Engineering gate before capturing the final demo

1. Run backend, script and runner regressions; frontend lint/typecheck/tests.
2. Rebuild the stack. Do not present old container acceptance as proof of current source.
3. `backend/.venv/Scripts/python.exe scripts/acceptance.py --base http://localhost:8080 --require-ai --env-file .env`.
   This now checks all artifact hashes, rehashes the result, checks backend/runner source
   identity, and requires the AMD planner, accepted plan execution and validated reporting.
   An upstream outage fails this **submission gate**, not the deterministic verdict engine.
4. `backend/.venv/Scripts/python.exe scripts/amd_benchmark.py --env-file .env -n 1` is a
   small real-endpoint sample, not a statistically robust performance claim. Record failures
   and the sample size; increase iterations only if quota/time allow.
5. Capture real browser walkthroughs on both profiles, plus unknown/re-evaluation/failure cases.
    Mark prerecorded playback and historical screenshots clearly.
   Regenerate the eight-slide deck/cover with `node scripts/export_pitch.mjs`; it checks layout,
   visible placeholders and source/export hashes. This does not record or publish a video.
6. Generate application dependency inventory; review notices, rights and source obligations.
7. Preserve old assessments. New manifests identify actual backend/engine/adapters and runner
   source contents; an image tag and contract version alone do not identify an implementation.
   `python scripts/release_evidence.py` records actual local image IDs/security settings and
   independently compares deployed backend/runner source fingerprints with this worktree.

## Public demo without unnecessary architecture changes

Current demo URL: **https://d1yxcnwgdgjzt6.cloudfront.net**. Infrastructure/viewer checks
and scoped cleanup are recorded in [`INFRA_AUDIT_2026-10-17.md`](INFRA_AUDIT_2026-10-17.md).
The deployed AWS application still predates the API budget and runner hardening
described below. HTTPS availability is not proof of those controls or fresh source identity.
Plan the reviewed release and strict acceptance before claiming them.

Use Compose v2.35+ and Docker Engine 26+ (runner volume subpath support). The API owns the DB.
Runners run as UID 10001, with all capabilities dropped and no egress; they mount only `runs/`.
They still share a trusted artifact namespace: this is not hostile multi-tenant isolation.
The current demo only executes pinned open-source fixtures, not arbitrary uploaded firmware.

The owner's judging policy explicitly requires **anonymous access without login**.
Use HTTPS and the public override's API budgets, not Basic Auth. Deployment credentials stay
with the operator; judges receive only the public viewer URL. The final deployment target
is **AWS only**; see [`../deploy/aws/README.md`](../deploy/aws/README.md).

```bash
docker compose -f docker-compose.yml -f docker-compose.public.yml up -d --build
```

Never commit `.env`, private keys or deployment credentials. Never combine public and dev overrides:
dev exposes port 8000 and intentionally bypasses the public gateway. The dev override binds
only to 127.0.0.1, avoiding accidental exposure on venue Wi-Fi. Bound active jobs and
POST requests with `RELEASEPROOF_MAX_ACTIVE_RUNS` / `RELEASEPROOF_MUTATION_RPM`.
This is an anonymous pinned-fixture demo, not a customer/tenant hosting service.

## Operator steps that cannot be fabricated

- [x] Owner confirmed solo team and lablab/ADP/Discord registration; recheck final event form/deadline.
- [x] Owner confirmed application/POC rights and disclosure of reuse (owner statement, not legal certification).
- [ ] Confirm contest MIT/prior-work interpretation if uncertain; retain organizer reply.
- [x] Existing public MIT repository and HTTPS demo URL independently opened; team recorded.
- [ ] Publish the reviewed final source/evidence and redeploy the frozen hardening to the demo.
- [ ] Add the authentic final video URL; verify all final links externally.
- [ ] Record/upload authentic MP4/MOV; regenerate/review PDF after final slide edits.
- [ ] Confirm anonymous HTTPS access; test both configurations from an external browser.
- [ ] Submit on lablab before cutoff; verify successful submission/receipt.

Owner confirmation received during remediation: Francesco Carpineti (solo team) confirmed
application/POC rights, disclosure of reuse and lablab/AMD ADP/Discord registration. The supplied
repository `https://github.com/francescocarpineti091299/release-proof` was independently opened
without authentication and shows Public/MIT. This is an owner declaration, not legal advice
or an organizer ruling on specific third-party distribution. The final demo video is not yet made.

`pitch/submission_fields.json` is the form-ready source of truth. It deliberately leaves
unprovided URLs/team/attestations blank until supplied. The existing CloudFront demo URL was
independently checked over HTTPS: health and AMD configuration are available, with managed
Token Factory traces. Its assistant prompt is still `assistant@1`, so this does **not** establish
that the final hardening is deployed there. Verify/redeploy the frozen release and its public
access policy before confirming `judge_access_verified=true`.
Check the fields without publishing anything:

```bash
python scripts/submission_check.py --acceptance docs/acceptance/<fresh-strict-report>.json
```

The checker refuses missing fields and older acceptance reports that lack the strengthened gates.

### Managed AMD transport

AMD documents that long generations should stream to keep connections active:
https://amd-aim.github.io/radeon-cloud-docs/api/chat-completions/ (17 October 2026).
Compose enables `AMD_LLM_STRUCTURED_STREAM=1`: planner/report/alternatives are collected from
the real SSE response in JSON mode, require the terminal marker, then undergo the **same** full
local schema/citation/verdict validation before persistence/display. No fragments count as an
accepted plan/report. Non-streaming behavior remains selectable with `=0` for endpoints that
require it; this is transport negotiation, never a fallback to another provider or old data.

Do not claim "perfect compliance" until these external checks are complete. UNKNOWN recovery,
an INCOMPATIBLE migration, or use of the same board with two different bootloaders are not
event violations and must not be manipulated into a positive result.

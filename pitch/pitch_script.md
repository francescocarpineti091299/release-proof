# ReleaseProof: live pitch talk track (< 5 min) + judge Q&A

Deck: `pitch/slides.pdf` (8 slides). Target **4:25**, which leaves a 35 s buffer. Bracketed timings
are cumulative. Speak slowly, because judges read the slides while you talk.

> Introduce yourself with the actual team name. Technical counts refer to labelled historical
> runs, not current-source acceptance. Economic inputs are hypothetical. Do not infer GPU identity,
> cloud deployment, customer support or measured ROI from this script.

---

## Slide 1 · Title · [0:00–0:20]

"This is **ReleaseProof**, a preflight check for industrial IoT firmware teams.

One sentence to remember: **a firmware can boot and still be impossible to upgrade safely.**
ReleaseProof checks the *migration path*, not just the new image. It uses real builds, real
emulation and a deterministic verdict. The AMD-hosted AI plans and explains, but it never decides."

## Slide 2 · Industrial problem · [0:20–0:55]

"A factory may depend on wireless sensors for condition monitoring. An OEM can build a secure
next-generation image and still discover that installed bootloaders cannot accept it. Physical
intervention can mean rework and gaps in monitoring.

Nordic documents nRF52840 in industrial sensors from NI, Lynxemi and Atomation—the MCU family in
our demo. We do not support their proprietary images or claim them as customers. Our first buyer
is the firmware lead or product-security manager at a sensor manufacturer.

On the right is what we measured. In the lab, the new ML-DSA-87 bootloader and image boot fine, so
the test is green. In the field, the deployed ECDSA bootloader receives the ML-DSA update and
answers *'Update type invalid'*, and version 1 keeps running. **Boots is not the same as migrates.**
Finding that out before rollout lets the engineer reconsider the update path."

## Slide 3 · Solution · [0:55–1:35]

"ReleaseProof makes that a repeatable check. You pick a supported configuration, with every
commit and toolchain pinned. You pick the change and click Run.

It really executes. It builds both bootloaders, signs with ephemeral keys, boots and updates in
Renode, and runs positive *and* negative tests. Every artifact gets a sha256 and every evidence row
links to it. This historical build/emulation run took 42 seconds, with 8 of 8 tests executed and
61 hashed artifacts. AI-enabled wall time is different. The candidate is compatible, the transition is incompatible.
Those are two separate questions with two separate answers."

## Slide 4 · Two configurations · [1:35–2:00]

"We support two configurations end to end, on the same Nordic nRF52840 chip.

With **wolfBoot**, the PQC candidate works. The problem is the *path*: there is no bootloader
self-update on this chip, and the old bootloader rejects the new image.

With **MCUboot on Zephyr 4.2**, the failure is different. The pinned imgtool refuses to produce an
ML-DSA signature at all. We measured that by running it. Single-stage MCUboot also can't replace
itself in the field.

The tests share bootloader-agnostic semantics, but each profile implements them differently. The
runners measure, and only the engine decides. A fact we didn't observe becomes UNKNOWN, never a
pass."

## Slide 5 · Agentic loop · [2:00–2:45]

"Here's where the AI fits. The AMD-hosted model **plans**: it picks optional tests from a registered
catalog, and it can't remove the required ones or invent new ones. The runner **executes**. The
deterministic engine **decides**. The AI then **explains** with citations to real evidence IDs and
**proposes** alternatives from an allowed set.

A human picks one, and that creates a *new* run. For wolfBoot, re-flashing the bootloader in a
service window removes the blocker, but the result is **INDETERMINATE**, not compatible, because we
never observed recovery from an interrupted update. That's an honest unknown.

The guardrails check structured schemas, citation IDs and explicit verdict phases. Chat is buffered
before validation. These checks do not prove the semantic truth of every sentence. Logs are untrusted
data; the AI has no shell or authority to change the verdict."

## Slide 6 · Architecture, AMD and limits · [2:45–3:25]

"The inference configuration is Google Gemma, Gemma-4-31B-IT, served on AMD Token Factory. The
managed GPU is undisclosed. In a small two-iteration comparison it completed 12 of 14 calls, with
two timeouts and every response schema-valid—not a
performance benchmark. The run's traces show what the AI actually did. If it is unavailable, we say
so; the deterministic pipeline continues without another provider.

The app uses isolated runners and a deterministic engine. AWS c7a on AMD EPYC is a deployment
target, not an attested cloud deployment. This is emulation, not silicon; power-loss recovery stays
unknown. A runner crash produces FAILED, not a firmware verdict."

## Slide 7 · Buyer, economics and packaging · [3:25–4:00]

"For a sensor OEM, a hypothetical fleet of 5,000 devices, with 5 percent requiring physical
intervention at 250 euros each, represents 62,500 euros of exposure. Every input is hypothetical;
this is not measured savings or a customer incident.

Start with one technical pilot on a specific board, bootloader and change. Proposed packaging is
paid custom-profile onboarding, then a profile subscription and assessment volume—not a per-device
service. The portable evidence pack and strict CI preflight CLI are implemented; production CI,
pricing and willingness to pay still need validation."

## Slide 8 · Landscape, roadmap and ask · [4:00–4:25]

"Inventory scanners help find what changes. OTA platforms deliver it. Finite State is an adjacent
competitor with evidence-linked release gates, so we do not claim to be the only one. Our focused
question is whether the deployed bootloader can reach the candidate state on a supported profile.

Next validation: real hardware and interrupted updates, then new profiles and OTA integrations.
We are looking for industrial sensor design partners. Don't ask only whether your firmware works.
Ask whether deployed devices can get there—before rollout. Thank you."

---

## Likely judge Q&A (crisp, honest answers)

**1. "Isn't this just wolfBoot's CI?"**
No. wolfBoot's upstream CI (`test-renode-nrf52.yml`) builds and boots *each* signing algorithm on its
own and tests a same-scheme v1→v2 update. That is exactly the check that comes back green here.
ReleaseProof adds the explicit cross-generation assessment (deployed ECDSA bootloader + ML-DSA
update), the bootloader field-update capability, negative tests, and a deterministic verdict that
separates candidate from transition. It also does this for a second, unrelated bootloader family
(MCUboot/Zephyr) with the same engine.

**2. "What's real and what's simulated?"**
The builds, signatures, keys and bootloaders are real: the actual upstream code at pinned commits,
compiled with pinned toolchains for every run. The *hardware* is emulated: Renode 1.16.1 runs the
real binaries on an emulated nRF52840. The UART text you saw comes from the real bootloader code.
What we don't model is listed openly: flash timing, power loss, and the interrupted-update window
(so INV-I4 stays UNKNOWN). Nothing is replayed in a LIVE run. Recorded reference runs are labelled
as such.

**3. "Why AMD?"**
There are two workloads. The runners compile cross-toolchains and run Renode emulation for every
assessment. That is x86-64, CPU-bound and parallel per run, so it fits an AMD EPYC host (EC2 c7a).
The reasoning steps need an open model with reliable structured output, served on high-memory GPUs
with bounded, validated responses. The recorded configuration uses the managed AMD Token Factory
API; dedicated vLLM on MI300X is an optional deployment, not the recorded one. Selected evidence
context is sent to the configured provider. *(Add measured numbers only if available: `[[AMD_LATENCY_P50]]`,
`[[AMD_SCHEMA_VALID_RATE]]`.)* We also enforce AMD-only at code level: the host allow-list has no
fallback provider.

**4. "What if the LLM hallucinates?"**
It can't change the outcome. The verdict comes from the deterministic engine before the explainer
runs. The explainer must echo the engine's verdicts exactly, and every statement must cite an
evidence ID that exists in this run. Otherwise the output is rejected (one repair retry for structured reports, then
`REJECTED`). The planner can only choose from registered templates, and unknown ones are blocked and
shown. Alternatives come only from the profile's allowed list. Log text is wrapped as untrusted data
against prompt injection. Chat is buffered and checked before release. Citation existence and
explicit verdict-phase checks are not semantic entailment of every claim; human review remains
necessary. The persisted engine verdict is independent of the explanation.

**5. "What's the business model?"**
A recurring subscription per configuration profile (device + bootloader + toolchain, kept pinned and
re-validated), usage pricing per assessment or as a CI release gate, and one-off onboarding for an
OEM's own board or bootloader fork. Go-to-market runs through the embedded integrators already
selling PQC readiness assessments. Prices are hypotheses to validate with design partners, and we
don't claim ROI.

**6. "CNSA 2.0 prefers LMS/XMSS for firmware signing. Why ML-DSA?"**
Correct, CNSA 2.0 recommends the SP 800-208 hash-based schemes for firmware signing. ML-DSA-87 is
also a CNSA 2.0 signature algorithm, and it's what wolfBoot supports at our pinned commit. The engine
is algorithm-agnostic. LMS is on the roadmap, and for MCUboot it depends on upstream PR #2707, which
was still in review. The transition problem (can the deployed bootloader get there?) is the same
whichever PQC scheme you pick.

**7. "Can I trust a verdict from an emulator?"**
Only within its observed scope. Image rejection is observed by executing real binaries on the
emulated configuration; field-update capability also uses source/configuration inspection.
Neither guarantees equivalent silicon behavior. Timing and power-loss facts are UNKNOWN, which is
why the re-flash alternative is INDETERMINATE and not COMPATIBLE. A hardware-in-the-loop runner is on
the roadmap.

**8. "How does this scale to my board and bootloader?"**
Each configuration is a profile (YAML) plus allow-listed runner templates and an adapter, against a
shared test vocabulary (E01, E02, E03, X01, E05, E11). We built the MCUboot/Zephyr profile from
scratch during the hackathon, including our own NVMC flash model. A profile is only promoted after it
passes the acceptance gate on fresh LIVE runs. That onboarding work is a paid service in our model.

**9. "Why not let the LLM read the logs and decide?"**
Because the decision has to be reproducible and auditable. The same evidence gives the same verdict
and the same canonical hash, and golden-hash regression tests guard the engine. An LLM verdict can't
offer that. We use the model where it adds value: choosing tests, explaining them in plain language
and proposing alternatives, all cross-checked.

**10. "How is this different from Binarly or ONEKEY?"**
They statically analyse binaries to inventory crypto (CBOM, PQC readiness) and support compliance
workflows. That tells you *what* is quantum-vulnerable. We *execute* the migration (build, sign,
boot, update, negative tests) for a specific pinned configuration and decide whether the deployed
fleet can reach the target. The two are complementary, and a CBOM finding is a natural trigger for a
ReleaseProof run. We haven't benchmarked head-to-head, so we don't claim to be better at what they do.

**Bonus 11. "What did the AI actually do in the runs we saw?"**
Answer with whatever is true at pitch time. If connected: "the planner chose and ordered the
optional checks, the explainer wrote the cited explanation, and the alternatives came from the
model. The traces are on the AMD AI tab for each run." If not: "nothing. The endpoint wasn't
connected, the UI shows `AI_UNAVAILABLE`, and the deterministic fallback ran every registered test.
That is the designed degradation, and no other provider was called."

**Bonus 12. "Is this a compliance certification or a regulatory PQC mandate?"**
No. Every result is labelled "Non-official engineering assessment". It gives engineers and auditors
traceable evidence (manifest, hashes, UART captures) to support CRA technical documentation, but the
compliance decision stays with the manufacturer and, where required, a notified body. The CRA does
not generally mandate ML-DSA or a universal PQC retrofit. CNSA 2.0 targets US National Security
Systems, not every industrial OEM; NIST IR 8547 is an initial public draft, not binding law.

**Bonus 13. "Can I gate a release today?"**
There is a strict CLI and a manual GitHub Actions integration for an existing trusted run. They
verify the pack and replay the engine; only complete COMPATIBLE candidate/transition/migration
verdicts pass. Both current demo profiles correctly block. No GitHub-hosted execution or production
OTA integration is attested. See `docs/RELEASE_GATE.md`.

# ReleaseProof: live pitch talk track (< 5 min) + judge Q&A

Deck: `pitch/slides.pdf` (10 slides). Target **4:40**, which leaves a 20 s buffer. Bracketed timings
are cumulative. Speak slowly, because judges read the slides while you talk.

> Placeholders in **[[…]]** must be replaced by measured values or the sentence dropped. **Never
> say a number that is not on a slide or in `submission.md`.**

---

## Slide 1 · Title · [0:00–0:25]

"Hi, I'm `[[TEAM]]`. This is **ReleaseProof**.

One sentence to remember: **a firmware can boot and still be impossible to upgrade safely.**
ReleaseProof checks the *migration path*, not just the new image. It uses real builds, real
emulation and a deterministic verdict. The AMD-hosted AI plans and explains, but it never decides."

## Slide 2 · Problem · [0:25–1:05]

"Post-quantum is no longer a research topic for embedded teams. NSA's CNSA 2.0 wants firmware
signing on quantum-resistant algorithms *exclusively* by 2030, and firmware signing has the earliest
deadline in the whole suite. The EU Cyber Resilience Act fully applies in December 2027, and products
must stay updatable. NIST's draft disallows ECDSA after 2035.

Those deadlines hit fleets that last 10 to 20 years, with bootloaders that trust ECDSA keys burned in
years ago.

On the right is what we measured. In the lab, the new ML-DSA-87 bootloader and image boot fine, so
the test is green. In the field, the deployed ECDSA bootloader receives the ML-DSA update and
answers *'Update type invalid'*, and version 1 keeps running. **Boots is not the same as migrates.**
Finding that out after shipping means recalls or truck rolls."

## Slide 3 · Solution, live · [1:05–1:40]

"ReleaseProof turns that into a one-minute check. You pick a verified configuration, with every
commit and toolchain pinned. You pick the change and click Run.

It really executes. It builds both bootloaders, signs with ephemeral keys, boots and updates in
Renode, and runs positive *and* negative tests. Every artifact gets a sha256 and every evidence row
links to it. This run took 42 seconds. The candidate is compatible, the transition is incompatible.
Those are two separate questions with two separate answers."

## Slide 4 · Two configurations · [1:40–2:15]

"We support two configurations end to end, on the same Nordic nRF52840 chip.

With **wolfBoot**, the PQC candidate works. The problem is the *path*: there is no bootloader
self-update on this chip, and the old bootloader rejects the new image.

With **MCUboot on Zephyr 4.2**, the failure is different. The pinned imgtool refuses to produce an
ML-DSA signature at all. We measured that by running it. Single-stage MCUboot also can't replace
itself in the field.

The tests share bootloader-agnostic semantics, but each profile implements them differently. The
runners measure, and only the engine decides. A fact we didn't observe becomes UNKNOWN, never a
pass."

## Slide 5 · Agentic loop · [2:15–2:55]

"Here's where the AI fits. The AMD-hosted model **plans**: it picks optional tests from a registered
catalog, and it can't remove the required ones or invent new ones. The runner **executes**. The
deterministic engine **decides**. The AI then **explains** with citations to real evidence IDs and
**proposes** alternatives from an allowed set.

A human picks one, and that creates a *new* run. For wolfBoot, re-flashing the bootloader in a
service window removes the blocker, but the result is **INDETERMINATE**, not compatible, because we
never observed recovery from an interrupted update. That's an honest unknown.

The guardrails: schema validation, a citation check, a verdict-echo check, an allow-listed AMD host
with no fallback, and log text treated as untrusted."

## Slide 6 · Architecture + AMD · [2:55–3:25]

"The architecture is one AMD EPYC host on AWS c7a running everything under Docker Compose: the UI,
the API and orchestrator, two isolated runners with no network, and the engine. All the reasoning
goes to an LLM on **AMD Instinct** through AMD Developer Cloud.
*(If measured:)* `[[AMD_MODEL]]` on `[[AMD_HARDWARE]]`, p50 `[[AMD_LATENCY_P50]]`,
`[[AMD_SCHEMA_VALID_RATE]]` schema-valid.
*(If not yet connected, say:)* the AMD endpoint key was still pending, so the runs you saw used the
deterministic fallback. The panel shows that openly, and no other provider was ever called."

## Slide 7 · Evidence & safeguards · [3:25–3:55]

"Four honest facts. **Result:** a blocker that boot-only testing misses, found in 42 seconds with
21 cited evidence items and 61 hashed artifacts. **Failure case:** when a runner dies mid-run, the run
is FAILED and there's no verdict. Our own gate also caught a Renode file download on the offline
network and refused to fake the result. **Limitation:** this is emulation, not silicon, with no
power-loss model yet, so we report UNKNOWN instead of guessing. **Safeguard:** the AI never changes
a verdict, and an engineer chooses and signs off."

## Slide 8 · Market + business model · [3:55–4:20]

"Analysts put PQC at about $2.8 billion by 2030 and secure boot and firmware security at about
$4.4 billion. The first wave of PQC spending is assessment and planning, which is exactly what we
do. CRA fines go up to 15 million euros or 2.5% of turnover.

We'd charge per device-configuration profile, per assessment or as a CI gate, plus onboarding for
custom boards. We go to market through the integrators who already sell PQC readiness work.
Pricing is a hypothesis we'll validate with design partners, and we claim no ROI numbers today."

## Slide 9 · Competition · [4:20–4:35]

"Binarly and ONEKEY inventory the crypto in your binaries. Memfault, Mender and Golioth ship the
update. wolfBoot's own CI tests each algorithm on its own. Nobody executes the *deployed-to-candidate
transition* and gives a deterministic verdict on it. We're complementary: a CBOM tells you what to
migrate, and we tell you whether you can get there."

## Slide 10 · Roadmap + ask · [4:35–4:50]

"Next: the live AMD benchmark, the public EPYC deployment, power-fail tests and more boards. We're
looking for design partners with ECDSA-signed fleets.
**A firmware can boot and still be impossible to upgrade safely, and ReleaseProof tells you which
one you have before you ship.** Thank you."

---

## Likely judge Q&A (crisp, honest answers)

**1. "Isn't this just wolfBoot's CI?"**
No. wolfBoot's upstream CI (`test-renode-nrf52.yml`) builds and boots *each* signing algorithm on its
own and tests a same-scheme v1→v2 update. That is exactly the check that comes back green here.
ReleaseProof adds what CI doesn't do: the cross-generation test (deployed ECDSA bootloader + ML-DSA
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
we control. AMD Instinct on AMD Developer Cloud gives us that without sending firmware evidence to a
closed API. *(Add measured numbers only if available: `[[AMD_LATENCY_P50]]`,
`[[AMD_SCHEMA_VALID_RATE]]`.)* We also enforce AMD-only at code level: the host allow-list has no
fallback provider.

**4. "What if the LLM hallucinates?"**
It can't change the outcome. The verdict comes from the deterministic engine before the explainer
runs. The explainer must echo the engine's verdicts exactly, and every statement must cite an
evidence ID that exists in this run. Otherwise the output is rejected (one repair retry, then
`REJECTED`). The planner can only choose from registered templates, and unknown ones are blocked and
shown. Alternatives come only from the profile's allowed list. Log text is wrapped as untrusted data
against prompt injection. The worst case is a missing explanation, never a wrong verdict.

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
For the questions we ask, yes. "Does this bootloader reject this image?" and "does a self-update
path exist?" depend on code and layout, not on analogue behaviour, and we observe them from the real
binaries. For timing and power-loss behaviour, no, and we say so: those facts are UNKNOWN, which is
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

**Bonus 12. "Is this a compliance certification?"**
No. Every result is labelled "Non-official engineering assessment". It gives engineers and auditors
traceable evidence (manifest, hashes, UART captures) to support CRA technical documentation, but the
compliance decision stays with the manufacturer and, where required, a notified body.

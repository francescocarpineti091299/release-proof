# ReleaseProof: rethinking the idea and the pitch (discussion draft)

> Purpose: a working document for discussing with colleagues **what ReleaseProof could become** and
> **how to tell it**. It is deliberately more ambitious than the hackathon deck. Anything marked
> **[verify]** is a claim or number we must check before it goes into anything public. Anything
> marked **[hypothesis]** is a bet we want to discuss, not a fact.

---

## 1. Diagnosis: what the current pitch does and what holds it back

**What is already excellent (keep it):**

- **The insight is real and sticky.** "A firmware can boot and still be impossible to upgrade
  safely" / "boots ≠ migrates" is a genuinely non-obvious idea that firmware engineers recognise.
- **The proof is real.** Real builds, real bootloaders, real emulation, negative tests, and a red/green
  split (candidate COMPATIBLE, transition INCOMPATIBLE) that anyone can grasp in 3 seconds.
- **The trust architecture is a differentiator:** AI proposes, the engine decides, and unknowns stay UNKNOWN.

**What holds it back:**

| Problem | Symptom in the current deck | Effect on the listener |
|---|---|---|
| It describes **what we built**, not **what changes for the customer** | Commits, run IDs, sha256, "8/8 tests, 61 artifacts" | The listener sees a well-built tool, not a company |
| **Defensive tone** | Nearly every slide has 2–3 disclaimers ("not attested", "historical", "hypothetical") | Comes across as unsure. Honesty is good, but it needs one home, not all of them |
| **The problem is too small** | "One OEM, one chip, one algorithm change, €62.5k exposure" | Sounds like a niche feature, not a market |
| **Single-state thinking** | "The deployed bootloader" (singular) | Real fleets are a *zoo* of generations, and that zoo is where the pain lives |
| **AI story is weak** | "AI picks optional tests and explains" | Sounds decorative. Investors will ask "why AI?" |
| **No "why now"** | CRA is mentioned only as "context, not proof" | No urgency, so no reason to buy this year |
| **No vision** | Roadmap = "more boards, HIL" | No sense of where this goes in 3–5 years |

**In one sentence:** we have a great *demo* of a great *insight*, but we pitch it as a *test report*.

---

## 2. The bigger idea: three possible framings

### Framing A: "Every device has a cryptographic expiry date" (PQC-led)

Every connected device shipped today trusts a signing key and algorithm (ECDSA/RSA) baked into its
bootloader or ROM. Industrial devices stay in the field for 10–20 years. Once a cryptographically
relevant quantum computer exists, anyone holding one can **forge firmware updates** for every device
that still trusts classical signatures. That means fleet takeover, not just a data leak.
The only defence is migrating the *root of trust* in the field, and most fleets have never tested
whether that is even possible.

- Pro: strong urgency, big narrative, regulation-backed (CNSA 2.0, NIST IR 8547, EU PQC roadmap).
- Con: "quantum is far away" objection; buyers may defer budget to 2028+.

### Framing B: "Can your fleet still be updated?" (updatability-led, PQC as the forcing function)

The question is wider than PQC. Every *structural* change can strand part of a fleet: algorithm,
key rotation or revocation after a leak, bootloader upgrade, new flash layout, anti-rollback counters,
new hardware revision, or a toolchain change. Today teams check that **the new firmware works**. Nobody
systematically checks that **every deployed generation can actually get there**.

- Pro: everyday pain (key rotation and bootloader changes happen *now*). PQC becomes the biggest and
  most visible instance, not the only one. Ties into regulatory duties to keep devices patchable.
- Con: broader means harder to explain in 10 seconds, so we need a sharp hook.

### Framing C: "Google Maps for firmware migrations" (product metaphor)

Your installed base is spread across many "locations" (hardware rev × bootloader version × keys ×
algorithm). Your target is one destination. ReleaseProof **maps every location, computes a route
for each one, proves every road segment by actually driving it in emulation, and flags devices
with no road at all** (stranded cohorts) before you send a single update.

- Pro: instantly understandable to non-experts. It turns "alternatives" into *pathfinding*, which is
  where the AI really adds value.
- Con: a metaphor, not a category. It needs Framing A or B underneath.

### Recommendation [hypothesis, to discuss]

**Category = B, urgency = A, explanation = C.**

> *"Every embedded fleet will have to change its root of trust: new keys, new bootloaders, and soon
> post-quantum signatures. ReleaseProof maps every generation in your installed base, finds a
> proven route to the new security state, and tells you which devices would be stranded before
> you ship."*

---

## 3. Key concepts that make the idea bigger

### 3.1 The Fleet Generation Matrix (the core product artefact)

Real fleets are not "one deployed bootloader". They are a matrix:

```
                    Candidate release R7 (ML-DSA, new layout)
Deployed gen.       Candidate?   Transition?   Route
---------------------------------------------------------------
HW rev A + BL 1.0     ✔            ✘            none: STRANDED (no BL self-update)
HW rev A + BL 1.2     ✔            ✔ via R6.5   bridge release (hybrid sig)
HW rev B + BL 1.2     ✔            ✔            direct
HW rev B + BL 2.0     ✔            ?            UNKNOWN: power-loss window not observed
```

- Each cell is a deterministic verdict backed by executed evidence (what we already do for one cell).
- **The red rows are the business case.** "12% of your installed base cannot reach PQC by any route"
  is a board-level statement. "Transition INCOMPATIBLE on run a39610" is not.
- The matrix maps directly onto how OEMs think: product lines, hardware revisions, release trains.

### 3.2 The Migration Graph: from "alternatives" to pathfinding

Today the AI proposes alternatives from an allowed list. Bigger version:

- States = (hardware, bootloader, keys, algorithm, layout). Edges = candidate updates/procedures.
- The AI **searches for routes** (e.g. "ship bridge release v1.5 with hybrid ECDSA+ML-DSA signature and
  a bootloader update first, then v2"). It is good at this because it is combinatorial and creative.
- The engine **verifies every edge by execution**. A route is only green if every edge is proven.
- Output: a **migration plan per cohort**, plus the cohorts with *no* route.

This finally gives a crisp answer to "why AI?": **AI explores the route space and the emulator proves
each route.** Same safety principle as today (AI never decides), but with a much bigger role.

### 3.3 Migratability by design (shift-left)

The cheapest moment to avoid a stranded fleet is **before the device ships**. Same engine, used as a
design-time gate on new products:

- Is there room for PQC signatures and keys? (ML-DSA-87: signature 4,627 B and public key 2,592 B,
  versus 64 B / 64 B for ECDSA P-256, so ~70× bigger) **[verify exact sizes per parameter set]**
- Does the bootloader have a field self-update path? Spare key slots? Revocation? Hybrid verification?
- Can the device survive an interrupted update?

→ A **Migratability Score** per product line. It's a KPI a CISO or product-compliance owner can track,
and it gives you a reason to be in the design phase, not just at release.

### 3.4 The AI as the onboarding engine (the business reason AI matters)

The real scaling bottleneck of this business is **profile onboarding**: every new chip/bootloader/fork
needs an adapter, runner templates and acceptance. Today that is consulting work.

[hypothesis] An agent that reads a customer's bootloader source, configuration and partition map,
**drafts the profile and test templates**, and lets the deterministic acceptance gate approve or reject
them, would turn weeks of services into days. That shifts gross margin from services to software.
This is the AI story investors care about.

---

## 4. Why now (to be source-checked before use)

1. **PQC standards are final.** NIST FIPS 203/204/205 published August 2024. Vendors (wolfBoot, MCUboot
   in progress) are adding ML-DSA/LMS. Migration questions move from theory to engineering. **[verify]**
2. **Deadlines exist on paper.** CNSA 2.0 (US NSS): software/firmware signing "prefer" CNSA 2.0 now,
   exclusive by 2030. NIST IR 8547 (draft): deprecate classical 112-bit security by 2030, disallow by
   2035. EU coordinated PQC roadmap (June 2025): start now, critical/high-risk use cases by ~2030.
   **[verify wording and scope; frame as "direction of travel", not as a mandate for all OEMs]**
3. **Device lifetimes outlast the deadlines.** An industrial sensor shipped in 2026 with a 15-year life
   is still in service in 2041. Devices designed **this year** decide whether that fleet is migratable.
4. **Regulators now care about updatability itself, not just security features:**
   - EU **CRA**: products must be able to receive security updates during the support period; reporting
     obligations from Sep 2026, main obligations Dec 2027. **[verify Annex I wording]**
   - Automotive **UN R156** (software update management): compatibility of an update with the target
     configuration must be ensured before it is delivered. **[verify, could be a very strong fit]**
   - Medical (US FDA, cyber devices): manufacturers must be able to deliver updates and patches.
     **[verify]**
5. **Real incidents show un-rotatable keys are a fleet-level problem.** For example, leaked or test
   platform keys that could not be rotated in the field across many device models (e.g. the 2023 MSI /
   Boot Guard key leak, PKfail 2024). **[verify details; use as "this already happens", not as a claim
   ReleaseProof would have prevented it]**

---

## 5. New storyline (10 slides, investor/colleague version)

| # | Slide | Core message (draft line) |
|---|---|---|
| 1 | **Hook** | "Every connected device you ship has a cryptographic expiry date. Can you extend it?" |
| 2 | **The trap** | Live red/green split: *works in the lab, can't migrate in the field.* (Current slide 2, simplified, no hashes.) |
| 3 | **It's not one device, it's a zoo** | A real fleet = N hardware revs × M bootloaders × K keys. Teams test the destination, never the journey from each starting point. |
| 4 | **Why now** | PQC standards final, 2030/2035 horizons, 15-year device lifetimes, CRA/R156 updatability duties. Devices designed in 2026 decide 2040. |
| 5 | **The product** | The Fleet Generation Matrix: every cohort × every candidate, each cell proven by execution. Red rows = stranded devices. |
| 6 | **How it works** | "AI finds the routes, the emulator drives them, the engine signs off, the engineer decides." One clean diagram. |
| 7 | **Proof** | What runs today: two real bootloader families, real builds, emulated boot+update, negative tests, two *different* blockers found automatically. One honest line on limits. |
| 8 | **Customer & business** | Wedge: paid PQC migration readiness assessment per product line → subscription CI gate on every release → migration planner integrated with OTA. Buyer: Head of Firmware / Product Security; budget owner: product compliance. |
| 9 | **Why us / moat** | Executable evidence (not static guesses), a growing profile library (chip × bootloader × version), deterministic and auditable verdicts, honest UNKNOWNs. |
| 10 | **Ask** | Design partners: 3 OEMs with a real fleet and a real migration on the roadmap. (+ funding/team ask if relevant.) |

**Appendix (this is where all the honesty goes):** pinned versions, run IDs, hashes, emulation limits,
AI guardrails, hypothetical economics. *One* "what's real vs roadmap" slide, linked from slide 7.

---

## 6. Ready-to-use pitches (drafts)

**One-liner**
> ReleaseProof tells embedded manufacturers whether every device already in the field can safely reach
> their next firmware, and proves it before rollout.

**10-second hook**
> Your new firmware boots in the lab. Half your fleet still can't install it. We find out before you ship.

**30 seconds**
> Connected devices live 10–20 years, but their root of trust (keys, bootloader, signature algorithm)
> is frozen the day they ship. Post-quantum cryptography, key rotations and bootloader upgrades all force
> that root of trust to change. Today teams test that the new firmware works, not that each deployed
> generation can actually get there. ReleaseProof maps every generation in the fleet, builds and runs
> the real bootloaders in emulation, and proves a route for each one, or flags the devices that would be
> stranded. AI explores the routes. A deterministic engine signs off.

**2 minutes:** slides 1, 2, 3, 5, 6, 8 above, in that order.

---

## 7. Product vision ladder

| Horizon | Product | Value | Status |
|---|---|---|---|
| **Today** | Single-cell assessment: 1 deployed state → 1 candidate, 2 bootloader families on nRF52840, emulated | Proves the insight; a strong demo | Built |
| **6–12 months** | **Fleet Generation Matrix** + CI gate + evidence pack for audits; hardware-in-the-loop runner for power-loss tests; 3–5 chip/bootloader families | Release gate per product line | [hypothesis] |
| **12–24 months** | **Migration Graph / route planner** (AI-searched, engine-verified), AI-assisted profile onboarding, Migratability Score at design time | Migration planning, design-phase presence | [hypothesis] |
| **24–48 months** | Integration with OTA/fleet platforms (cohort data in, staged rollout plan out), with SBOM/CBOM tools (finding → assessment) and with silicon-vendor reference designs | System of record for "can this fleet change?" | [hypothesis] |

---

## 8. Business model and go-to-market hypotheses

All of these are **[hypothesis]** and should be validated with interviews.

- **Wedge: PQC Migration Readiness Assessment.** Fixed-fee, per product line: matrix + stranded-cohort
  report + recommended route + evidence pack. Easy to buy (services-like budget), fast to deliver.
- **Expand: Release gate subscription.** Every new release is checked against every deployed generation,
  priced per product line or profile (not per device).
- **Platform: Migration planner.** Priced on number of product lines and cohorts, integrated with OTA.
- **Channels to discuss:**
  - **Silicon vendors** (Nordic, ST, NXP…): want to sell "PQC-ready" chips; a migration-verified reference
    design is a sales asset for them.
  - **Bootloader / crypto vendors** (wolfSSL, commercial MCUboot forks): same logic.
  - **Embedded consultancies** already selling PQC readiness: ReleaseProof as their tooling.
  - **OTA platforms** (Memfault, Mender, Foundries.io): partners, not competitors. They deliver, we pre-verify.
- **Market sizing:** do it **bottom-up**, not with aggregated "IoT security market" numbers:
  `# OEMs with signed-boot product lines in target verticals × product lines per OEM × ACV`.
  Fill this together, with sources.

---

## 9. Moat and the hard questions we must be ready for

**Possible moats:**
1. **Profile library.** Every chip × bootloader × version onboarded and acceptance-gated is reusable
   across customers, so value compounds.
2. **Executable evidence.** Static scanners infer; we run. Hard to fake, easy to audit.
3. **Deterministic, auditable verdicts.** Fits regulated documentation (CRA tech file, R156 SUMS, FDA).
4. **Trust posture.** UNKNOWN is never green, and the AI never decides. That is a selling point for
   security buyers.

**Hard questions (and our current honest answer):**

| Question | Honest answer today | What would make it stronger |
|---|---|---|
| "Can't the bootloader vendor do this in their CI?" | Their CI tests same-scheme updates; cross-generation is not their job | Show a matrix across *multiple* vendors, which a single vendor won't build |
| "Emulation isn't silicon." | True. Power-loss and timing stay UNKNOWN | HIL runner on dev kits; position emulation as fast pre-screen + HIL as confirmation |
| "Onboarding every board is consulting, not SaaS." | True today | AI-assisted profile onboarding + library reuse |
| "Quantum is 10+ years away, why pay now?" | Devices shipped now are in the field then; key rotation/bootloader changes are today's pain | Lead with updatability (Framing B), PQC as forcing function |
| "Proprietary bootloaders?" | Not supported | Adapter SDK; start with open bootloaders (huge share of MCU market) **[verify]** |
| "Finite State / Binarly will add this." | Possible. They are adjacent | Speed, depth on transitions, partner rather than fight (CBOM finding → our assessment) |

---

## 10. Questions to decide together

1. **Framing:** PQC-led (A), updatability-led (B), or both (B with A as urgency)? My recommendation is B+A.
2. **First vertical:** industrial sensors (fits the demo), **automotive (UN R156 may be the strongest
   regulatory fit)**, medical devices, or smart metering (very long lifetimes)?
3. **Buyer vs budget owner:** Head of Firmware (champion) vs Product Security / Compliance (budget)?
   Who signs the PO?
4. **Wedge:** sell an assessment (services-like) first, or the CI gate (product-like) first?
5. **Emulation-first or HIL early?** How much of the value survives with only emulation?
6. **Is "key rotation / revocation" a better day-one use case than PQC?** More frequent, more urgent,
   same engine.
7. **Name:** does "ReleaseProof" still fit if the product is about *fleets and routes*, not *releases*?
   (Keep for now. Revisit once the category is settled.)
8. **Which 10 people do we interview first** to validate the stranded-cohort pain and willingness to pay?

---

## 11. What NOT to lose from the current version

- **Never let the AI decide**, and never turn UNKNOWN into a pass. That's the brand.
- **No fake numbers.** The new pitch is bigger in *vision*, not looser with *facts*. Keep every
  hypothesis labelled, but in **one place** (appendix), not on every slide.
- **The live red/green moment** is still the best 10 seconds of the whole pitch. Keep it on slide 2.

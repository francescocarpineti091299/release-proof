# ReleaseProof: demo video script (≤ 3:00) + 60-second backup

**Goal:** an *authentic* screen recording of the running app. It shows two real LIVE runs, an
alternative re-evaluated as a new run, and the AMD AI panel. Nothing is mocked or animated. Every
cut and speed-up is labelled on screen.

---

## 0. Before you record (checklist)

| # | Check | Why |
|---|---|---|
| 1 | Stack up: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d` (or the public `[[DEMO_URL]]`). Do one warm-up run per profile first (ccache, page caches) | First runs are slower |
| 2 | AMD endpoint configured (`AMD_LLM_*` in `.env`). Open `/amd` and check that the provider/model show `[[AMD_MODEL]]` on `[[AMD_HARDWARE]]` and that OK calls exist | The AI plan card, the explanation and the AMD panel should show real AMD calls |
| 3 | If the AMD endpoint is **not** connected at recording time, use the lines marked **[NO-AMD]** and never pretend otherwise | The UI shows `AI_UNAVAILABLE`, and the video must match |
| 4 | Browser: Chrome, 1920×1080 window, zoom 110%, bookmarks bar hidden, dark OS theme, notifications off | Readability |
| 5 | Recorder: OBS 1080p30, system audio off, separate mic track. Note the **wall-clock time** at each "Run assessment" click | For overlays |
| 6 | Have tab 1 on `/` and tab 2 on `/` | Fast switching |

**Overlay spec (added in editing):** bottom-left lower third, mono font, white on 80% navy:
`LIVE run · <run_id> · recorded <YYYY-MM-DD HH:MM UTC>`. Speed-ups show a top-right badge `⏩ ×4`.
Cuts show a 0.5 s badge `✂ <n> s of run time cut`. If this video is used as the fallback for a live
demo, add a permanent top-right badge `RECORDED DEMO`.

Run IDs to overlay (fill in after recording): `[[RUN_ID_WOLFBOOT]]`, `[[RUN_ID_REEVAL]]`,
`[[RUN_ID_MCUBOOT]]`. Reference runs already recorded on 17 Oct 2026 can be used as B-roll:
`RP-20261017T124806Z-a39610` (wolfBoot), `RP-20261017T124931Z-72d0b1` (re-evaluation),
`RP-20261017T124230Z-7682fc` (MCUboot), `RP-20261017T124942Z-23dd8f` (failed run).

---

## 1. Shot-by-shot (target 2:55)

### Shot 1 · 0:00–0:12 · Hook (home page hero)
- **Screen:** `/` hero, "A firmware can boot and still be impossible to upgrade safely." Slow
  2% zoom-in.
- **Say:** "Post-quantum deadlines are coming for firmware signing: CNSA 2.0 by 2030, and the EU
  Cyber Resilience Act from December 2027. But a firmware can boot and still be impossible to
  upgrade safely. ReleaseProof checks the migration path, not just the new image."

### Shot 2 · 0:12–0:28 · Pick configuration and change
- **Click:** wolfBoot card → **Select →**. Then the change row **"Migrate firmware signatures from
  ECDSA P-256 to ML-DSA-87"**. The *Review the planned checks* step appears.
- **Hover** briefly over **Always run (6)** and **AI may add (2)**.
- **Say:** "I pick a verified configuration: Nordic nRF52840 with wolfBoot, every commit and
  toolchain pinned. The change is ECDSA P-256 to ML-DSA-87. Six checks always run. The AMD-hosted
  planner can only add checks from this registered list. It cannot invent tests."

### Shot 3 · 0:28–0:36 · Start the LIVE run
- **Click:** green **Run assessment**. The run page opens.
- **Overlay:** `LIVE run · [[RUN_ID_WOLFBOOT]] · recorded [[RECORDING_TIME]]`.
- **Say:** "This is a live run. Nothing is replayed."

### Shot 4 · 0:36–0:55 · Pipeline streaming
- **Screen:** stage timeline: *Preparing → AI verification plan → Discovering → Building & signing →
  Running emulator tests*. The first 8 s run in real time, the rest at **⏩ ×4** (badge).
- **Point at** the AI verification plan card.
- **Say (AMD connected):** "The AI plan comes from `[[AMD_MODEL]]` on AMD Instinct. It ordered the
  optional checks and explained why. Now the runner builds both bootloaders, signs the images with
  fresh keys and boots them in Renode, including the negative tests: a tampered image, and the
  deployed bootloader receiving the new ML-DSA update."
- **Say [NO-AMD]:** "The AMD endpoint isn't connected in this recording, so the planner reports
  AI unavailable and the full deterministic plan runs. No other model is used. Now the runner…"
  (continue as above).

### Shot 5 · 0:55–1:25 · The verdict: boots ≠ migrates
- **Screen:** the Decision card: **INCOMPATIBLE**, *Candidate: Compatible*,
  *Transition: Incompatible*. Hold for 3 s.
- **Click:** under *Main causes*, the **EV-E11-SELF-UPDATE** citation chip. The evidence row
  flashes (source-inspection lines, `RAM_CODE=0`).
- **Scroll** to the *Tests* table and stop on **X01**: *"Update type invalid 0xB01!=0x200 … version
  1 before and after reset"*.
- **Say:** "Here's the trap. The ML-DSA candidate boots, so a per-algorithm boot test is green. But
  the deployed ECDSA bootloader rejects the update, and wolfBoot has no self-update path on this
  chip. So the transition is incompatible. Every claim links to evidence and hashed artifacts, and
  this verdict came from a deterministic engine, not from the AI."

### Shot 6 · 1:25–1:50 · Alternative → re-evaluation as a new run
- **Scroll** to **What AI suggests**. Point at the purple notice "These are proposals. They do not
  change the current result."
- **Click:** **Evaluate this plan** on *Re-flash the bootloader during a field-service maintenance
  window*. The new run page opens.
- **Overlay:** `REEVALUATION · [[RUN_ID_REEVAL]] · parent [[RUN_ID_WOLFBOOT]]`.
- **Screen:** yellow banner "Re-evaluation of plan field_service_reflash on evidence from run … The
  parent run and its verdict are unchanged." Then **INDETERMINATE**, and *Main causes* **INV-I4
  Unknown**.
- **Say:** "The AI proposes, but a human chooses. Re-flashing in a service window removes the
  blocker. It still isn't a pass, because recovery from an interrupted update was never observed.
  The result is indeterminate, an honest unknown, and the original run is untouched."

### Shot 7 · 1:50–2:25 · Second configuration: MCUboot
- **Click:** top nav **New assessment** → MCUboot card **Select →** → **"Migrate firmware signatures
  from ECDSA P-256 to ML-DSA"** → **Run assessment**.
- **Overlay:** `LIVE run · [[RUN_ID_MCUBOOT]] · recorded [[RECORDING_TIME]]`. Show 5 s of
  streaming, then cut with the badge `✂ ~55 s of run time cut`.
- **Screen:** **INCOMPATIBLE**, with both *Candidate* and *Transition* Incompatible. Scroll to
  **Tests without a pass**: *pqc_signing=REJECTED with imgtool 2.2.0 … 'ml-dsa-65' is not one of
  …*.
- **Say:** "Same chip, a different bootloader, and a different failure. The pinned MCUboot
  toolchain refuses to produce an ML-DSA signature. We measured that by actually running it, we
  didn't assume it. And single-stage MCUboot can't be replaced in the field. Different checks,
  same engine."

### Shot 8 · 2:25–2:45 · AMD panel
- **Click:** top nav **AMD AI**. Show the *Provider*, *Hardware* `[[AMD_HARDWARE]]`, *AI calls*,
  *Latency (OK calls)* `[[AMD_LATENCY_P50]]` and *Fallback provider: None* tiles, then *Models per
  module*.
- *(Optional, if time allows: on the wolfBoot run click **Ask about this run** and ask "Why is the
  transition incompatible?". Show the cited answer for 4 s.)*
- **Say (AMD connected):** "Every AI step runs on one AMD-hosted endpoint: `[[AMD_MODEL]]` on
  `[[AMD_HARDWARE]]`, with a p50 latency of `[[AMD_LATENCY_P50]]` and `[[AMD_SCHEMA_VALID_RATE]]`
  schema-valid outputs. There is no fallback provider, and outputs that cite missing evidence or
  contradict the verdict are rejected."
- **Say [NO-AMD]:** "Every AI step is wired to one AMD-hosted endpoint, with no fallback provider.
  It's not connected in this recording, and the panel says so."

### Shot 9 · 2:45–2:58 · Safety + close
- **Screen:** 2 s on the failed run `RP-20261017T124942Z-23dd8f`: "Run failed: no verdict issued ·
  TOOL_FAILURE". Then the end card (`cover.png` + `[[DEMO_URL]]` + `[[GITHUB_URL]]`).
- **Say:** "If a tool fails, there's no verdict. We never fake a result. ReleaseProof: know whether
  your fleet can actually get there, before you ship."

**Total ≈ 2:58.** If you run long, cut the optional assistant in Shot 8 first, then shorten Shot 4.

---

## 2. Backup version: 60 seconds

Use the already-recorded runs (overlay their real IDs). Recording date: 17 Oct 2026.

| Time | Screen | Say |
|---|---|---|
| 0:00–0:08 | Home hero | "A firmware can boot and still be impossible to upgrade safely. ReleaseProof checks the migration path." |
| 0:08–0:18 | Wizard: wolfBoot → ECDSA P-256 → ML-DSA-87 → **Run assessment**, then ⏩ ×8 through the pipeline | "Real builds, fresh keys, boot and update tests in Renode on an emulated nRF52840." |
| 0:18–0:32 | Decision of `RP-20261017T124806Z-a39610` → X01 row | "The ML-DSA candidate boots, but the deployed bootloader rejects the update and can't replace itself. Transition incompatible, decided by a deterministic engine with linked evidence." |
| 0:32–0:42 | **Evaluate this plan** → `RP-20261017T124931Z-72d0b1` INDETERMINATE | "The AI proposes a field re-flash, a human evaluates it as a new run, and the result is indeterminate: an honest unknown, not a pass." |
| 0:42–0:52 | MCUboot `RP-20261017T124230Z-7682fc` → imgtool refusal | "On MCUboot the pinned tool refuses ML-DSA, measured live. A different failure caught by the same engine." |
| 0:52–1:00 | `/amd` panel → end card | "AI runs on AMD-hosted inference, with no fallback, and it never decides. `[[DEMO_URL]]`." |

---

## 3. Do / don't

- **Do** keep the browser URL bar visible in at least Shots 3, 6 and 7 (the run IDs are in the URL).
- **Do** label every speed-up and cut. **Don't** splice the verdict of one run onto the
  pipeline of another.
- **Don't** say "certified", "compliant" or "proves the firmware is secure". The UI says
  "Non-official engineering assessment" and the narration must match.
- **Don't** show `.env`, API keys or the AMD endpoint URL with credentials.

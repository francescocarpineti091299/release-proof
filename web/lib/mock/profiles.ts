import type { ConfigurationView, Profile, TestCatalog } from "@/lib/types";

/** Mirrors profiles/*.yaml and profiles/test_catalog.yaml (mock mode only). */

export const MOCK_PROFILES: Profile[] = [
  {
    id: "nrf52840-wolfboot-pqc",
    version: "1.0",
    status: "SUPPORTED",
    title: "Nordic nRF52840 + wolfBoot",
    description:
      "nRF52840 (Cortex-M4F) emulated in Renode with the wolfBoot secure bootloader pinned to the commit used by the WP0 reference run. Supports a classical-to-post-quantum signature migration.",
    board: {
      id: "nordic-nrf52840",
      name: "Nordic nRF52840",
      soc: "nRF52840 (Arm Cortex-M4F, 1 MB flash, 256 KB RAM)",
      emulator: "renode",
      platform_script: "platforms/cpus/nrf52840.repl",
    },
    bootloader: {
      family: "wolfboot",
      name: "wolfBoot",
      repo: "https://github.com/wolfSSL/wolfBoot",
      commit: "4c79eee999b7083743811f37928322fe78b9fdb1",
      version_label: "master@4c79eee (nearest tag v2.9.0, ancestry unproven)",
      license: "GPL-3.0 (fetched at build time inside the runner image; not redistributed)",
    },
    toolchain: {
      renode: "1.16.1",
      "arm-none-eabi-gcc": "14.2.rel1",
      wolfcrypt_commit: "4aa1ad7a5b4f7be86d88cc26fe3880a31ff7de9f",
    },
    runner: { service: "runner-wolfboot", image: "releaseproof/runner-wolfboot:0.1.0", timeout_seconds: 900 },
    assessment_adapter: "wolfboot_v1_2",
    ruleset_version: "1.2",
    changes: [
      {
        change_id: "ecdsa_p256_to_mldsa87",
        title: "Migrate firmware signatures from ECDSA P-256 to ML-DSA-87",
        summary:
          "Replace the classical signature verified by the bootloader with the post-quantum ML-DSA-87 (FIPS 204, CNSA 2.0) signature, on devices already deployed with an ECDSA bootloader.",
        from_scheme: "ECDSA_P256",
        to_scheme: "ML_DSA_87",
        default_plan_id: "bootloader_self_update",
        default_plan_title: "Over-the-air bootloader self-update, then ML-DSA firmware",
        required_templates: [
          "wolfboot.discover",
          "wolfboot.self_update_capability",
          "wolfboot.boot_current",
          "wolfboot.boot_candidate",
          "wolfboot.tampered_image_rejected",
          "wolfboot.cross_generation_update",
        ],
        optional_templates: ["wolfboot.candidate_rejects_classical", "wolfboot.dual_signature_build"],
        alternatives: [
          {
            plan_id: "field_service_reflash",
            title: "Re-flash the bootloader during a field-service maintenance window",
            description:
              "A technician replaces the ECDSA bootloader with the ML-DSA bootloader through the debug port in a planned maintenance window, then the ML-DSA firmware is installed.",
            mechanism: "field_service_reflash",
            requires_rerun_tests: false,
            status: "EXECUTABLE",
          },
          {
            plan_id: "staged_hybrid_dual_signature",
            title: "Staged hybrid bootloader accepting ECDSA and ML-DSA",
            description:
              "Ship an intermediate bootloader that verifies both signatures, then move to ML-DSA only. Requires a working dual-signature build on the pinned commit.",
            mechanism: "hybrid_dual_signature",
            requires_rerun_tests: true,
            status: "EXECUTABLE",
          },
        ],
      },
    ],
    known_limitations: [
      "Renode models nRF52840 flash as plain memory (no NVMC); erase/write timing faults are not reproduced.",
      "RAM usage comes from the linker region, not from runtime stack measurement.",
      "The interrupted-update (non-atomic window) behaviour is not observed; it stays UNKNOWN.",
    ],
  },
  {
    id: "nrf52840-mcuboot-pqc",
    version: "1.0",
    status: "EXPERIMENTAL",
    title: "Nordic nRF52840 + MCUboot (Zephyr)",
    description:
      "nRF52840 emulated in Renode running MCUboot built with Zephyr sysbuild and a demo application. Same chip as the wolfBoot profile, different bootloader family and update model.",
    board: {
      id: "nordic-nrf52840",
      name: "Nordic nRF52840",
      soc: "nRF52840 (Arm Cortex-M4F, 1 MB flash, 256 KB RAM)",
      emulator: "renode",
      platform_script: "platforms/boards/nrf52840dk_nrf52840.repl + releaseproof NVMC model",
    },
    bootloader: {
      family: "mcuboot",
      name: "MCUboot",
      repo: "https://github.com/zephyrproject-rtos/mcuboot",
      commit: "PIN_AT_SPIKE",
      version_label: "Zephyr v4.2.0 manifest revision",
      license: "Apache-2.0",
    },
    toolchain: { renode: "1.16.1", zephyr: "v4.2.0", "zephyr-sdk": "0.17.4" },
    runner: { service: "runner-mcuboot", image: "releaseproof/runner-mcuboot:0.1.0", timeout_seconds: 1200 },
    assessment_adapter: "mcuboot_v1_2",
    ruleset_version: "1.2",
    changes: [
      {
        change_id: "ecdsa_p256_to_mldsa",
        title: "Migrate firmware signatures from ECDSA P-256 to ML-DSA",
        summary:
          "Move the MCUboot-verified firmware signature to a post-quantum scheme on devices already deployed with an ECDSA P-256 MCUboot.",
        from_scheme: "ECDSA_P256",
        to_scheme: "ML_DSA",
        default_plan_id: "mcuboot_field_update",
        default_plan_title: "Over-the-air MCUboot replacement, then ML-DSA firmware",
        required_templates: [
          "mcuboot.discover",
          "mcuboot.bootloader_update_capability",
          "mcuboot.boot_current",
          "mcuboot.tampered_image_rejected",
          "mcuboot.pqc_sign_attempt",
          "mcuboot.cross_key_update",
        ],
        optional_templates: ["mcuboot.signed_update"],
        alternatives: [
          {
            plan_id: "depot_reflash_mcuboot",
            title: "Re-flash MCUboot at a service depot",
            description:
              "Devices are returned to a depot and MCUboot is re-flashed by debug probe. Removes the field-update blocker but not the lack of a post-quantum verifier.",
            mechanism: "depot_physical_reflash",
            requires_rerun_tests: false,
            status: "EXECUTABLE",
          },
          {
            plan_id: "switch_to_wolfboot_depot",
            title: "Replace MCUboot with a PQC-capable bootloader (wolfBoot) at a depot",
            description:
              "Changes bootloader family. Must be assessed as a new configuration (see the nRF52840 + wolfBoot profile); not provable from this run's evidence.",
            mechanism: "bootloader_family_change",
            requires_rerun_tests: false,
            status: "REQUIRES_EXTERNAL_VALIDATION",
          },
          {
            plan_id: "mcuboot_lms_branch",
            title: "Adopt the upstream MCUboot LMS work (PR #2707)",
            description:
              "Hash-based LMS signatures are in review upstream and simulator-only. Not executable on the pinned toolchain.",
            mechanism: "upstream_feature_pending",
            requires_rerun_tests: false,
            status: "REQUIRES_EXTERNAL_VALIDATION",
          },
        ],
      },
    ],
    known_limitations: [
      "Renode has no nRF52840 NVMC model upstream; ReleaseProof ships a minimal one (status/ready, page erase).",
      "Single-image MCUboot; no hardware crypto (CryptoCell) is emulated.",
      "The interrupted-swap behaviour is not observed; it stays UNKNOWN.",
    ],
  },
];

export const MOCK_CATALOG: TestCatalog = {
  version: "1.0",
  tests: {
    D01: "Source, toolchain and configuration discovery",
    E01: "Current (deployed) state boots with the classical signature",
    E02: "Candidate state boots with the post-quantum signature",
    E03: "Image with an invalid signature is rejected",
    E04: "Image header and manifest coherence",
    E05: "Signed image fits the boot slot",
    E08: "Valid firmware update is applied",
    E11: "Bootloader can be updated in the field",
    E12: "Interrupted bootloader update recovers (non-atomic window)",
    O05: "Dual-signature (hybrid) policy builds and is observable",
    P01: "Candidate bootloader rejects classically-signed images (PQC-only policy)",
    X01: "Deployed bootloader receives a candidate-signed update (cross-generation)",
  },
  templates: [
    t("wolfboot.discover", "D01", "wolfboot", "Discover pinned source, toolchain and partition layout", "Records wolfBoot/wolfCrypt commits, tool versions and the nRF52840 partition map from the pinned config.", "Pins and layout recorded", 5),
    t("wolfboot.self_update_capability", "E11", "wolfboot", "Bootloader self-update capability (source inspection)", "Inspects the pinned HAL and example configs for a supported bootloader self-update path on this board.", "Capability recorded as SUPPORTED or UNSUPPORTED", 5),
    t("wolfboot.boot_current", "E01", "wolfboot", "Build, sign and boot the current ECDSA P-256 image", "Builds wolfBoot with SIGN=ECC256, signs v1 and v2 test images, boots v1 in Renode and applies the v2 update.", "Version 1 boots; version 2 update applied", 60),
    t("wolfboot.boot_candidate", "E02", "wolfboot", "Build, sign and boot the candidate ML-DSA-87 image", "Builds wolfBoot with SIGN=ML_DSA level 5, signs images, boots in Renode and measures signed size against the boot slot.", "Version 1 boots; signed image fits the slot", 70),
    t("wolfboot.tampered_image_rejected", "E03", "wolfboot", "Tampered image is rejected (negative)", "Flips one byte of the signed factory image and boots it; the bootloader must refuse it.", "Boot refused (no application version frame)", 40, true),
    t("wolfboot.cross_generation_update", "X01", "wolfboot", "Deployed ECDSA bootloader receives an ML-DSA-signed update (negative)", "Boots the deployed ECDSA bootloader with a v1 ECDSA image and stages a v2 update signed with ML-DSA-87.", "Update not applied (device stays on version 1)", 70, true),
    t("wolfboot.candidate_rejects_classical", "P01", "wolfboot", "Candidate ML-DSA bootloader rejects an ECDSA-signed image (negative)", "Boots the candidate ML-DSA-87 bootloader with an ECDSA-signed factory image to observe the authorization policy.", "Boot refused (PQC-only policy observed)", 50, true),
    t("wolfboot.dual_signature_build", "O05", "wolfboot", "Hybrid dual-signature build (ECDSA + ML-DSA)", "Attempts SIGN=ECC256 SIGN_SECONDARY=ML_DSA on the pinned commit.", "Build outcome recorded", 60),
    t("mcuboot.discover", "D01", "mcuboot", "Discover pinned source, toolchain, partitions and signing algorithms", "Records Zephyr/MCUboot pins, the flash partition map from zephyr.dts and the key types supported by imgtool.", "Pins, partitions and algorithms recorded", 10),
    t("mcuboot.bootloader_update_capability", "E11", "mcuboot", "Bootloader field-update capability (partition map + config)", "Checks whether the built configuration provides any partition or mechanism to replace MCUboot in the field.", "Capability recorded as SUPPORTED or UNSUPPORTED", 5),
    t("mcuboot.boot_current", "E01", "mcuboot", "Build, sign and boot the current ECDSA P-256 image", "Builds MCUboot (ECDSA P-256) and the demo application v1 with Zephyr, signs with imgtool and boots in Renode.", "MCUboot validates slot 0 and the application reports version 1", 120),
    t("mcuboot.signed_update", "E08", "mcuboot", "Valid signed update v1 -> v2 is applied", "Stages a v2 image signed with the deployed key in slot 1 and reboots.", "MCUboot swaps and the application reports version 2", 60),
    t("mcuboot.tampered_image_rejected", "E03", "mcuboot", "Tampered update is rejected (negative)", "Stages a v2 image with one flipped payload byte in slot 1 and reboots.", "MCUboot rejects slot 1; version 1 keeps running", 60, true),
    t("mcuboot.pqc_sign_attempt", "E02", "mcuboot", "Produce a post-quantum (ML-DSA) signed image with the pinned imgtool", "Attempts to generate an ML-DSA key and sign the candidate image with the pinned MCUboot imgtool.", "Signed image produced, or refusal recorded with the tool output", 10),
    t("mcuboot.cross_key_update", "X01", "mcuboot", "Deployed bootloader receives an update signed with a new key (negative)", "Stages a v2 image signed with a key the deployed MCUboot does not embed and reboots.", "MCUboot rejects the update; version 1 keeps running", 60, true),
  ],
};

function t(
  template_id: string,
  test_id: string,
  family: "wolfboot" | "mcuboot",
  title: string,
  description: string,
  expected: string,
  est_seconds: number,
  negative = false,
) {
  return { template_id, test_id, family, title, description, expected, est_seconds, negative, params_schema: { type: "object" } };
}

export function mockTemplate(id: string) {
  return MOCK_CATALOG.templates.find((x) => x.template_id === id);
}

/** Same projection the API does for GET /api/configurations. */
export const MOCK_CONFIGS: ConfigurationView[] = MOCK_PROFILES.map((p) => ({
  id: p.id,
  version: p.version,
  status: p.status,
  title: p.title,
  description: p.description,
  board: p.board,
  bootloader: p.bootloader,
  toolchain: p.toolchain,
  runner_image: p.runner.image,
  timeout_seconds: p.runner.timeout_seconds,
  ruleset_version: p.ruleset_version,
  known_limitations: p.known_limitations,
  changes: p.changes.map((c) => {
    const templates = [...c.required_templates, ...c.optional_templates].map((id) => {
      const t = mockTemplate(id)!;
      return {
        template_id: t.template_id,
        test_id: t.test_id,
        title: t.title,
        description: t.description,
        negative: t.negative,
        expected: t.expected,
        est_seconds: t.est_seconds,
        required: c.required_templates.includes(id),
      };
    });
    return {
      change_id: c.change_id,
      title: c.title,
      summary: c.summary,
      from_scheme: c.from_scheme,
      to_scheme: c.to_scheme,
      default_plan_id: c.default_plan_id,
      default_plan_title: c.default_plan_title,
      templates,
      alternatives: c.alternatives,
      est_seconds_total: templates.reduce((a, t) => a + t.est_seconds, 0),
    };
  }),
}));
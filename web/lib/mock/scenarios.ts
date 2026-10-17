/* Mock-mode fixtures. Values are realistic but synthetic, and the UI labels them MOCK DATA. */
import type {
  AIAlternativesView,
  AIModule,
  AIPlanView,
  AIReportView,
  AssessmentDoc,
  FailureView,
  LogStream,
  PlannedBy,
  RunMode,
  SemanticResult,
  Stage,
  StageStatus,
  TestOutcome,
  FailureClass,
} from "@/lib/types";
import wp0Raw from "./data/wp0-baseline.json";
import conditionalRaw from "./data/scenario-conditional.json";

export type ScenarioKey =
  | "wolfboot"
  | "wolfboot-hybrid"
  | "mcuboot"
  | "mcuboot-failed"
  | "reeval-reflash"
  | "reeval-mcuboot"
  | "reference";

export type LogLine = [LogStream, string];

export interface MockTest {
  template_id: string;
  test_id: string;
  planned_by: PlannedBy;
  outcome: TestOutcome;
  observed: string;
  duration_ms: number;
  stage: Stage;
  failure_class?: FailureClass;
  observation_ids: string[];
  logs: LogLine[];
}

export interface MockArtifact {
  artifact_id: string;
  name: string;
  kind: string;
  size_bytes: number;
  test_id: string | null;
  stage: Stage;
}

export interface MockTrace {
  module: AIModule;
  stage: Stage;
  prompt_template: string;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  status: "OK" | "AI_UNAVAILABLE" | "SCHEMA_INVALID" | "REJECTED_BY_GUARDRAIL";
  error?: string;
}

export interface ScenarioSpec {
  key: ScenarioKey;
  configuration_id: string;
  configuration_version: string;
  change_id: string;
  plan_id: string;
  mode: RunMode;
  /** Stages that never run for this kind of run (e.g. re-evaluation). */
  skipped: Stage[];
  /** Final status override per stage (default SUCCEEDED). */
  stageFinal: Partial<Record<Stage, { status: StageStatus; message: string }>>;
  failAt?: Stage;
  failure?: FailureView;
  tests: MockTest[];
  stageLogs: Partial<Record<Stage, LogLine[]>>;
  artifacts: MockArtifact[];
  aiPlan?: Omit<AIPlanView, "trace_ids">;
  aiReport?: Omit<AIReportView, "trace_ids">;
  aiAlternatives?: Omit<AIAlternativesView, "trace_ids">;
  doc?: { assessment: AssessmentDoc; result: SemanticResult };
  traces: MockTrace[];
  source_pins: Record<string, string>;
  tool_versions: Record<string, string>;
  /** Evidence run id: this run (LIVE) or the parent (REEVALUATION); "keep" = as recorded. */
  evidenceRun: "self" | "parent" | "keep";
}

type Doc = { assessment: AssessmentDoc; result: SemanticResult };

function clone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x)) as T;
}

const WP0 = wp0Raw as unknown as Doc;
const CONDITIONAL = conditionalRaw as unknown as Doc;

// ------------------------------------------------------------------ shared wolfBoot pieces

const WOLFBOOT_PINS = {
  wolfboot: "4c79eee999b7083743811f37928322fe78b9fdb1",
  wolfcrypt: "4aa1ad7a5b4f7be86d88cc26fe3880a31ff7de9f",
  runner_image: "releaseproof/runner-wolfboot@sha256:5b0e7c1d9a4f2e8b6c3d1a0f9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d",
};

const WOLFBOOT_TOOLS = {
  renode: "1.16.1.32457",
  "arm-none-eabi-gcc": "14.2.rel1",
  python: "3.12.7",
  "wolfboot-keytools": "sign@4c79eee",
};

function ccLines(prefix: string, files: string[]): LogLine[] {
  return files.map((f) => ["build", `${prefix} CC ${f}`] as LogLine);
}

const WOLFBOOT_SRC = [
  "src/string.c",
  "src/image.c",
  "src/libwolfboot.c",
  "src/loader.c",
  "src/boot_arm.c",
  "src/update_flash.c",
  "hal/nrf52.c",
  "lib/wolfssl/wolfcrypt/src/sha256.c",
  "lib/wolfssl/wolfcrypt/src/hash.c",
  "lib/wolfssl/wolfcrypt/src/memory.c",
  "lib/wolfssl/wolfcrypt/src/wc_port.c",
];

function wolfbootPlanTests(withP01: boolean, withO05: boolean): MockTest[] {
  const tests: MockTest[] = [
    {
      template_id: "wolfboot.discover",
      test_id: "D01",
      planned_by: "POLICY_REQUIRED",
      outcome: "PASS",
      observed: "wolfBoot 4c79eee, wolfCrypt 4aa1ad7; boot slot 256 KiB, sector 4 KiB",
      duration_ms: 3120,
      stage: "DISCOVERY",
      observation_ids: ["OBS-D01-bootloader_commit", "OBS-D01-crypto_commit", "OBS-D01-partition_layout"],
      logs: [
        ["tool", "git -C /work/wolfBoot rev-parse HEAD -> 4c79eee999b7083743811f37928322fe78b9fdb1"],
        ["tool", "git -C /work/wolfBoot/lib/wolfssl rev-parse HEAD -> 4aa1ad7a5b4f7be86d88cc26fe3880a31ff7de9f"],
        ["tool", "parse config/examples/nrf52840.config: WOLFBOOT_PARTITION_SIZE=0x40000 WOLFBOOT_SECTOR_SIZE=0x1000"],
        ["runner", "D01 PASS: pins and layout recorded"],
      ],
    },
    {
      template_id: "wolfboot.self_update_capability",
      test_id: "E11",
      planned_by: "POLICY_REQUIRED",
      outcome: "PASS",
      observed: "UNSUPPORTED: no bootloader self-update path for nRF52840 in the pinned HAL",
      duration_ms: 2410,
      stage: "DISCOVERY",
      observation_ids: ["OBS-E11-bootloader_field_update"],
      logs: [
        ["tool", "scan hal/nrf52.c for RAM_CODE flash routines and WOLFBOOT_SELF_UPDATE hooks"],
        ["tool", "scan config/examples/nrf52840*.config: RAM_CODE=0, no self-update example"],
        ["runner", "E11 PASS: capability recorded as UNSUPPORTED (hal/nrf52.c)"],
      ],
    },
    {
      template_id: "wolfboot.boot_current",
      test_id: "E01",
      planned_by: "POLICY_REQUIRED",
      outcome: "PASS",
      observed: "Version 1 booted; version 2 update applied (UART 'Version: 2')",
      duration_ms: 48230,
      stage: "EMULATION_TESTS",
      observation_ids: ["OBS-E01-boot_outcome", "OBS-E01-observed_version", "OBS-E08-update_outcome"],
      logs: [
        ["renode", "Renode 1.16.1 :: loading platforms/cpus/nrf52840.repl"],
        ["renode", "sysbus LoadBinary @/work/out/ecc256/factory.bin 0x0"],
        ["uart", "wolfBoot v2.9.0 [ECC256]"],
        ["uart", "Boot partition: 0x10000 (size 262144)"],
        ["uart", "Verifying signature... OK"],
        ["uart", "Test App: Version: 1"],
        ["renode", "staging v2 image in update partition 0x50000"],
        ["uart", "Update started. Swapping sectors..."],
        ["uart", "Test App: Version: 2"],
        ["runner", "E01 PASS: v1 booted, v2 applied (uart.log:L4-L9)"],
      ],
    },
    {
      template_id: "wolfboot.boot_candidate",
      test_id: "E02",
      planned_by: "POLICY_REQUIRED",
      outcome: "PASS",
      observed: "Version 1 booted with ML-DSA-87; signed image 12,876 B fits 262,144 B slot",
      duration_ms: 55410,
      stage: "EMULATION_TESTS",
      observation_ids: ["OBS-E02-boot_outcome", "OBS-E05-layout_fit", "OBS-E04-image_header"],
      logs: [
        ["renode", "sysbus LoadBinary @/work/out/mldsa87/factory.bin 0x0"],
        ["uart", "wolfBoot v2.9.0 [ML_DSA level 5]"],
        ["uart", "Verifying signature... OK"],
        ["uart", "Test App: Version: 1"],
        ["runner", "E02 PASS: candidate boots; header span 12288 B, signed size 12876 B"],
      ],
    },
    {
      template_id: "wolfboot.tampered_image_rejected",
      test_id: "E03",
      planned_by: "POLICY_REQUIRED",
      outcome: "PASS",
      observed: "Boot refused: signature check failed, no version frame within 20 s",
      duration_ms: 31870,
      stage: "EMULATION_TESTS",
      observation_ids: ["OBS-E03-auth_negative"],
      logs: [
        ["tool", "flip byte at offset 0x1a3 of factory_v1_signed.bin (sha256 changes)"],
        ["uart", "wolfBoot v2.9.0 [ML_DSA level 5]"],
        ["uart", "Verifying signature... FAILED"],
        ["uart", "wolfBoot: panic()"],
        ["runner", "E03 PASS (negative): rejection positively identified by panic marker (uart.log:L3-L4)"],
      ],
    },
    {
      template_id: "wolfboot.cross_generation_update",
      test_id: "X01",
      planned_by: "POLICY_REQUIRED",
      outcome: "PASS",
      observed: "Update not applied: deployed ECDSA bootloader kept version 1 after staging the ML-DSA image",
      duration_ms: 61240,
      stage: "EMULATION_TESTS",
      observation_ids: ["OBS-X01-cross_update_outcome"],
      logs: [
        ["uart", "wolfBoot v2.9.0 [ECC256]"],
        ["uart", "Test App: Version: 1"],
        ["renode", "staging ML-DSA-87 signed v2 in update partition"],
        ["uart", "Update: signature verification failed, keeping current image"],
        ["uart", "Test App: Version: 1"],
        ["runner", "X01 PASS (negative): update REJECTED, old version kept running (uart.log:L2-L5)"],
      ],
    },
  ];
  if (withP01)
    tests.push({
      template_id: "wolfboot.candidate_rejects_classical",
      test_id: "P01",
      planned_by: "AI_PLANNER",
      outcome: "PASS",
      observed: "Boot refused: candidate ML-DSA bootloader did not accept the ECDSA image",
      duration_ms: 38020,
      stage: "EMULATION_TESTS",
      observation_ids: ["OBS-P01-classical_image_on_candidate"],
      logs: [
        ["uart", "wolfBoot v2.9.0 [ML_DSA level 5]"],
        ["uart", "Verifying signature... FAILED"],
        ["uart", "wolfBoot: panic()"],
        ["runner", "P01 PASS (negative): PQC-only policy observed"],
      ],
    });
  if (withO05)
    tests.push({
      template_id: "wolfboot.dual_signature_build",
      test_id: "O05",
      planned_by: withP01 ? "AI_PLANNER" : "POLICY_REQUIRED",
      outcome: "PASS",
      observed: "BUILD_FAILED: SIGN_SECONDARY=ML_DSA not supported with SIGN=ECC256 on the pinned commit",
      duration_ms: 22150,
      stage: "BUILD_SIGN",
      observation_ids: ["OBS-O05-dual_signature_build"],
      logs: [
        ["build", "make SIGN=ECC256 SIGN_SECONDARY=ML_DSA ML_DSA_LEVEL=5 TARGET=nrf52"],
        ["build", "options.mk:812: *** Unsupported SIGN_SECONDARY combination.  Stop."],
        ["runner", "O05 PASS: build outcome recorded (BUILD_FAILED)"],
      ],
    });
  return tests;
}

const WOLFBOOT_BUILD_LOGS: LogLine[] = [
  ["build", "make TARGET=nrf52 SIGN=ECC256 HASH=SHA256 (deployed generation)"],
  ...ccLines("[ecc256]", WOLFBOOT_SRC),
  ["build", "[ecc256] LD wolfboot.elf"],
  ["build", "[ecc256] wolfboot.bin: 23652 bytes"],
  ["sign", "tools/keytools/sign --ecc256 test-app/image.bin wolfboot_signing_private_key.der 1"],
  ["sign", "tools/keytools/sign --ecc256 test-app/image.bin wolfboot_signing_private_key.der 2"],
  ["build", "make TARGET=nrf52 SIGN=ML_DSA ML_DSA_LEVEL=5 (candidate generation)"],
  ...ccLines("[mldsa87]", [...WOLFBOOT_SRC, "lib/wolfssl/wolfcrypt/src/wc_mldsa.c", "lib/wolfssl/wolfcrypt/src/sha3.c"]),
  ["build", "[mldsa87] LD wolfboot.elf"],
  ["build", "[mldsa87] wolfboot.bin: 22840 bytes"],
  ["sign", "tools/keytools/sign --ml_dsa test-app/image.bin wolfboot_signing_private_key.der 1"],
  ["sign", "image_v1_signed.bin: 12876 bytes (header 12288)"],
];

const WOLFBOOT_ARTIFACTS: MockArtifact[] = [
  { artifact_id: "art-ecc256-wolfboot-bin", name: "ecc256/wolfboot.bin", kind: "bin", size_bytes: 23652, test_id: "E01", stage: "BUILD_SIGN" },
  { artifact_id: "art-ecc256-v1-signed", name: "ecc256/test-app_image_v1_signed.bin", kind: "signed_image", size_bytes: 840, test_id: "E01", stage: "BUILD_SIGN" },
  { artifact_id: "art-mldsa87-wolfboot-bin", name: "wolfboot.bin", kind: "bin", size_bytes: 22840, test_id: "E02", stage: "BUILD_SIGN" },
  { artifact_id: "art-mldsa87-v1-signed", name: "test-app_image_v1_signed.bin", kind: "signed_image", size_bytes: 12876, test_id: "E02", stage: "BUILD_SIGN" },
  { artifact_id: "art-nrf52840-config", name: "config/examples/nrf52840.config", kind: "config", size_bytes: 1184, test_id: "D01", stage: "DISCOVERY" },
  { artifact_id: "art-hal-nrf52", name: "hal/nrf52.c", kind: "other", size_bytes: 9431, test_id: "E11", stage: "DISCOVERY" },
  { artifact_id: "art-mismatch-resc", name: "mismatch.resc", kind: "script", size_bytes: 612, test_id: "E03", stage: "EMULATION_TESTS" },
  { artifact_id: "art-uart-e01", name: "E01/uart.log", kind: "uart", size_bytes: 2210, test_id: "E01", stage: "EMULATION_TESTS" },
  { artifact_id: "art-uart-e03", name: "E03/uart.log", kind: "uart", size_bytes: 980, test_id: "E03", stage: "EMULATION_TESTS" },
  { artifact_id: "art-uart-x01", name: "X01/uart.log", kind: "uart", size_bytes: 1740, test_id: "X01", stage: "EMULATION_TESTS" },
  { artifact_id: "art-manifest", name: "manifest.json", kind: "manifest", size_bytes: 6120, test_id: null, stage: "EVALUATION" },
];

function wolfbootDoc(): Doc {
  const doc = clone(WP0);
  doc.assessment.evidence = [
    ...(doc.assessment.evidence ?? []),
    {
      id: "EV-X01-CROSS-UPDATE",
      evidence_kind: "MEASUREMENT",
      source_role: "TOOL",
      authority_context: "OBSERVED",
      acquisition_mode: "EMULATED",
      review_status: "AUTOMATIC",
      status: "VALID",
      test_id: "X01",
      artifact_refs: ["X01/uart.log"],
      value: "REJECTED",
    },
  ];
  return doc;
}

const PLANNER_TRACE: MockTrace = {
  module: "planner",
  stage: "AI_PLAN",
  prompt_template: "planner/v3",
  latency_ms: 2140,
  prompt_tokens: 2861,
  completion_tokens: 412,
  status: "OK",
};
const EXPLAINER_TRACE: MockTrace = {
  module: "explainer",
  stage: "NEXT_STEPS",
  prompt_template: "explainer/v2",
  latency_ms: 3870,
  prompt_tokens: 6904,
  completion_tokens: 655,
  status: "OK",
};
const ALTERNATIVES_TRACE: MockTrace = {
  module: "alternatives",
  stage: "NEXT_STEPS",
  prompt_template: "alternatives/v2",
  latency_ms: 3110,
  prompt_tokens: 5230,
  completion_tokens: 540,
  status: "OK",
};

const WOLFBOOT_AI_PLAN: Omit<AIPlanView, "trace_ids"> = {
  status: "OK",
  message: "",
  blocked_templates: ["wolfboot.interrupted_update_recovery"],
  proposal: {
    summary:
      "The plan depends on a bootloader self-update, so self-update capability and the cross-generation update are the decisive checks. Added the PQC-only policy check to make the candidate's authorization behaviour observable. Skipped the hybrid build because it does not apply to this plan.",
    selected: [
      { template_id: "wolfboot.self_update_capability", priority: 1, rationale: "The default plan requires the deployed bootloader to replace itself over the air; this is the first possible blocker." },
      { template_id: "wolfboot.cross_generation_update", priority: 2, rationale: "Shows whether firmware-only delivery could bypass the bootloader change." },
      { template_id: "wolfboot.candidate_rejects_classical", priority: 3, rationale: "Makes the candidate authorization policy (PQC-only vs. hybrid) observable for invariant INV-I3." },
    ],
    skipped: [
      { template_id: "wolfboot.dual_signature_build", reason: "The selected plan is a direct ECDSA to ML-DSA switch; a hybrid build is only relevant to the staged hybrid alternative." },
    ],
    suggested_new_tests: [
      { title: "Interrupted bootloader update (power cut mid-swap)", purpose: "Would make the non-atomic update window (INV-I4) observable. No registered implementation exists, so it is not executed." },
    ],
  },
};

const WOLFBOOT_AI_REPORT: Omit<AIReportView, "trace_ids"> = {
  status: "OK",
  message: "",
  report: {
    headline: "The ML-DSA-87 image boots, but deployed devices cannot get there: the bootloader cannot be updated in the field.",
    verdict_echo: { migration: "INCOMPATIBLE", candidate: "INDETERMINATE", transition: "INCOMPATIBLE" },
    main_causes: [
      { text: "The plan needs an over-the-air bootloader self-update, and inspection of the pinned wolfBoot HAL for nRF52840 found no supported self-update path.", citations: ["REQ-BOOT-S0S1", "EV-E11-SELF-UPDATE"] },
      { text: "The deployed ECDSA bootloader refused the ML-DSA-signed update in emulation, so shipping new firmware alone cannot work around it.", citations: ["EV-X01-CROSS-UPDATE"] },
      { text: "Recovery from an interrupted update and the dual-signature policy were not observed, so the candidate state is not proven either.", citations: ["INV-I4", "GAP-E12-NON-ATOMIC", "GAP-O05-DUAL-POLICY"] },
    ],
    verified: [
      { text: "Current ECDSA image boots and applies a v1 to v2 update.", citations: ["EV-E01-BOOT"] },
      { text: "Candidate ML-DSA-87 image boots in Renode.", citations: ["EV-E02-BOOT"] },
      { text: "A tampered image is rejected.", citations: ["EV-E03-PANIC"] },
      { text: "The signed candidate image fits the boot partition.", citations: ["EV-E05-LAYOUT-G2", "EV-LAYOUT-PARTITION"] },
    ],
    unknowns: [
      { text: "Behaviour when an update is interrupted mid-swap.", citations: ["GAP-E12-NON-ATOMIC", "GAP-E10-INTERRUPT"] },
      { text: "Runtime RAM and stack usage of the ML-DSA verifier.", citations: ["GAP-E07-RAM"] },
    ],
    executive_summary:
      "Booting the new image is not the problem. Getting devices that already run the ECDSA bootloader onto the ML-DSA bootloader is. On this board and commit there is no field self-update path, and the old bootloader rejects ML-DSA updates. Unless the delivery mechanism changes, the migration cannot proceed as planned.",
  },
};

const WOLFBOOT_AI_ALTERNATIVES: Omit<AIAlternativesView, "trace_ids"> = {
  status: "OK",
  message: "",
  alternatives: {
    proposals: [
      {
        plan_id: "field_service_reflash",
        title: "Re-flash the bootloader during a field-service maintenance window",
        rationale: "Replaces the bootloader through the debug port instead of over the air, which removes the self-update requirement that blocks the default plan.",
        addresses: ["REQ-BOOT-S0S1"],
        preconditions: ["Physical or debug-port access to each device", "A scheduled maintenance window"],
        tradeoffs: ["Operational cost per device", "Slower rollout"],
        evidence_still_needed: ["Interrupted-update behaviour (E12) remains unobserved"],
      },
      {
        plan_id: "staged_hybrid_dual_signature",
        title: "Staged hybrid bootloader accepting ECDSA and ML-DSA",
        rationale: "An intermediate bootloader that accepts both signatures would avoid a hard cut-over. The dual-signature build must be proven first, so this requires a new live run.",
        addresses: ["INV-I3"],
        preconditions: ["A dual-signature build on the pinned commit"],
        tradeoffs: ["Still needs one bootloader replacement", "Larger image header"],
        evidence_still_needed: ["O05 dual-signature build and boot"],
      },
    ],
    not_addressable: ["INV-I4: interrupted-update recovery is not observable in the current emulation model (no NVMC fault injection)."],
  },
};

// ------------------------------------------------------------------ MCUboot

const MCUBOOT_PINS = {
  mcuboot: "9f2d6c41b7e05a3c8d1e2f4a6b7c8d9e0f1a2b3c",
  zephyr: "v4.2.0 (4e1c5a7f0b8d2e3f4a5b6c7d8e9f0a1b2c3d4e5f)",
  runner_image: "releaseproof/runner-mcuboot@sha256:a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0",
};

const MCUBOOT_TOOLS = {
  renode: "1.16.1.32457",
  "zephyr-sdk": "0.17.4",
  west: "1.3.0",
  imgtool: "2.2.0",
  cmake: "3.30.5",
};

const MCUBOOT_BUILD_LOGS: LogLine[] = [
  ["build", "west build -b nrf52840dk/nrf52840 --sysbuild samples/releaseproof_app -- -DSB_CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256=y"],
  ["build", "-- Zephyr version: 4.2.0 (/work/zephyr), build: v4.2.0"],
  ["build", "-- Board: nrf52840dk, qualifiers: nrf52840"],
  ...ccLines("[mcuboot]", ["boot/bootutil/src/loader.c", "boot/bootutil/src/image_validate.c", "boot/bootutil/src/image_ecdsa.c", "boot/bootutil/src/swap_move.c", "boot/zephyr/main.c", "boot/zephyr/flash_map_extended.c"]),
  ["build", "[mcuboot] Memory region  FLASH: 41216 B / 48 KB (83.85%)"],
  ...ccLines("[app]", ["src/main.c", "src/version.c"]),
  ["build", "[app] Memory region  FLASH: 36028 B / 464 KB (7.58%)"],
  ["sign", "imgtool sign --key root-ec-p256.pem --header-size 0x200 --align 4 --version 1.0.0 --slot-size 0x74000 zephyr.bin app_v1.signed.bin"],
  ["sign", "imgtool sign --key root-ec-p256.pem --version 2.0.0 ... app_v2.signed.bin"],
];

function mcubootTests(): MockTest[] {
  return [
    {
      template_id: "mcuboot.discover",
      test_id: "D01",
      planned_by: "POLICY_REQUIRED",
      outcome: "PASS",
      observed: "MCUboot 9f2d6c4, Zephyr v4.2.0; slot0/slot1 464 KiB; imgtool key types: rsa, ecdsa-p256/p384, ed25519, x25519",
      duration_ms: 7420,
      stage: "DISCOVERY",
      observation_ids: ["OBS-D01-bootloader_commit", "OBS-D01-partition_layout", "OBS-D01-imgtool_key_types"],
      logs: [
        ["tool", "west manifest --freeze -> mcuboot 9f2d6c41b7e0, zephyr v4.2.0"],
        ["tool", "parse build/zephyr/zephyr.dts: boot_partition 0xc000, slot0 @0xc000 0x74000, slot1 @0x80000 0x74000"],
        ["tool", "imgtool keygen --help: -t [rsa-2048|rsa-3072|ecdsa-p256|ecdsa-p384|ed25519|x25519]"],
        ["runner", "D01 PASS"],
      ],
    },
    {
      template_id: "mcuboot.bootloader_update_capability",
      test_id: "E11",
      planned_by: "POLICY_REQUIRED",
      outcome: "PASS",
      observed: "UNSUPPORTED: single-stage MCUboot, no bootloader slot or serial recovery in the built config",
      duration_ms: 1980,
      stage: "DISCOVERY",
      observation_ids: ["OBS-E11-bootloader_field_update"],
      logs: [
        ["tool", "check .config: CONFIG_BOOT_SERIAL_UART not set, no mcuboot_secondary partition"],
        ["runner", "E11 PASS: capability recorded as UNSUPPORTED"],
      ],
    },
    {
      template_id: "mcuboot.boot_current",
      test_id: "E01",
      planned_by: "POLICY_REQUIRED",
      outcome: "PASS",
      observed: "MCUboot validated slot 0; application reports version 1",
      duration_ms: 41250,
      stage: "EMULATION_TESTS",
      observation_ids: ["OBS-E01-boot_outcome", "OBS-E01-observed_version", "OBS-E05-layout_fit"],
      logs: [
        ["renode", "Renode 1.16.1 :: nrf52840dk_nrf52840.repl + releaseproof NVMC model"],
        ["uart", "*** Booting MCUboot v2.2.0 ***"],
        ["uart", "I: Primary image: magic=unset, swap_type=0x1, copy_done=0x3, image_ok=0x3"],
        ["uart", "I: Bootloader chainload address offset: 0xc000"],
        ["uart", "*** Booting Zephyr OS build v4.2.0 ***"],
        ["uart", "releaseproof-app version=1"],
        ["runner", "E01 PASS"],
      ],
    },
    {
      template_id: "mcuboot.tampered_image_rejected",
      test_id: "E03",
      planned_by: "POLICY_REQUIRED",
      outcome: "PASS",
      observed: "Slot 1 rejected (image validation failed); version 1 kept running",
      duration_ms: 39880,
      stage: "EMULATION_TESTS",
      observation_ids: ["OBS-E03-auth_negative"],
      logs: [
        ["tool", "flip payload byte 0x400 of app_v2.signed.bin"],
        ["uart", "*** Booting MCUboot v2.2.0 ***"],
        ["uart", "E: Image in the secondary slot is not valid!"],
        ["uart", "releaseproof-app version=1"],
        ["runner", "E03 PASS (negative): rejection identified by 'not valid' marker"],
      ],
    },
    {
      template_id: "mcuboot.pqc_sign_attempt",
      test_id: "E02",
      planned_by: "POLICY_REQUIRED",
      outcome: "PASS",
      observed: "Refusal recorded: pinned imgtool has no ML-DSA key type (signing_result REJECTED)",
      duration_ms: 2310,
      stage: "BUILD_SIGN",
      observation_ids: ["OBS-E02-pqc_signing"],
      logs: [
        ["sign", "imgtool keygen -t ml-dsa-65 -k candidate.pem"],
        ["sign", "Error: Invalid value for '-t' / '--type': 'ml-dsa-65' is not one of 'rsa-2048', 'rsa-3072', 'ecdsa-p256', 'ecdsa-p384', 'ed25519', 'x25519'."],
        ["runner", "E02 PASS: refusal recorded with tool output"],
      ],
    },
    {
      template_id: "mcuboot.cross_key_update",
      test_id: "X01",
      planned_by: "POLICY_REQUIRED",
      outcome: "PASS",
      observed: "Update rejected: key not embedded in deployed MCUboot; version 1 kept running",
      duration_ms: 40470,
      stage: "EMULATION_TESTS",
      observation_ids: ["OBS-X01-cross_update_outcome"],
      logs: [
        ["uart", "*** Booting MCUboot v2.2.0 ***"],
        ["uart", "E: Image in the secondary slot is not valid!"],
        ["uart", "releaseproof-app version=1"],
        ["runner", "X01 PASS (negative)"],
      ],
    },
    {
      template_id: "mcuboot.signed_update",
      test_id: "E08",
      planned_by: "AI_PLANNER",
      outcome: "PASS",
      observed: "Swap completed; application reports version 2",
      duration_ms: 44120,
      stage: "EMULATION_TESTS",
      observation_ids: ["OBS-E08-update_outcome"],
      logs: [
        ["uart", "I: Starting swap using move algorithm."],
        ["uart", "releaseproof-app version=2"],
        ["runner", "E08 PASS"],
      ],
    },
  ];
}

const MCUBOOT_ARTIFACTS: MockArtifact[] = [
  { artifact_id: "art-zephyr-dts", name: "build/zephyr/zephyr.dts", kind: "config", size_bytes: 18240, test_id: "D01", stage: "DISCOVERY" },
  { artifact_id: "art-mcuboot-bin", name: "mcuboot/zephyr.bin", kind: "bin", size_bytes: 41216, test_id: "E01", stage: "BUILD_SIGN" },
  { artifact_id: "art-app-v1", name: "app_v1.signed.bin", kind: "signed_image", size_bytes: 36540, test_id: "E01", stage: "BUILD_SIGN" },
  { artifact_id: "art-imgtool-log", name: "E02/imgtool.log", kind: "log", size_bytes: 412, test_id: "E02", stage: "BUILD_SIGN" },
  { artifact_id: "art-uart-e03", name: "E03/uart.log", kind: "uart", size_bytes: 1320, test_id: "E03", stage: "EMULATION_TESTS" },
  { artifact_id: "art-uart-x01", name: "X01/uart.log", kind: "uart", size_bytes: 1290, test_id: "X01", stage: "EMULATION_TESTS" },
  { artifact_id: "art-manifest", name: "manifest.json", kind: "manifest", size_bytes: 5480, test_id: null, stage: "EVALUATION" },
];

function ev(id: string, test_id: string, acquisition_mode: string, value: unknown, artifact_refs: string[] = [], kind = "MEASUREMENT") {
  return {
    id,
    evidence_kind: kind,
    source_role: "TOOL",
    authority_context: "OBSERVED",
    acquisition_mode,
    review_status: "AUTOMATIC",
    status: "VALID",
    test_id,
    artifact_refs,
    value,
  };
}

function row(
  key: "requirement_id" | "invariant_id",
  id: string,
  phase: string,
  subject_type: string,
  subject_ref: string,
  state: string,
  critical: boolean,
  evidence_refs: string[],
  gap_refs: string[] = [],
) {
  return {
    [key]: id,
    phase,
    subject_type,
    subject_ref,
    state,
    critical_for_verdict: critical,
    evidence_refs,
    gap_refs,
    rule_refs: key === "invariant_id" ? [id] : [],
    provenance: evidence_refs.length ? "MEASUREMENT" : gap_refs.length ? "GAP" : "CONSTRAINT",
    findings: [],
  };
}

function mcubootDoc(): Doc {
  const assessment: AssessmentDoc = {
    assessment_id: "MCUBOOT-LIVE",
    contract_version: "1.2",
    created_at: "2026-10-17T10:42:11Z",
    profile: {
      id: "PROFILE-NRF52840-MCUBOOT",
      requirements: [
        { id: "REQ-PQC-SIGN", criterion: "Candidate image can be signed with the target post-quantum scheme by the pinned tooling", critical_for_verdict: true },
        { id: "REQ-BOOT-S0S1", criterion: "Declared transition requires replacing MCUboot in the field; unsupported field update blocks the transition", critical_for_verdict: true },
        { id: "REQ-AUTH-NEGATIVE", criterion: "Deployed verifier rejects images with an invalid or unknown signature (E03, X01)", critical_for_verdict: false },
        { id: "REQ-LAYOUT", criterion: "Signed image fits the boot slot", critical_for_verdict: true },
        { id: "REQ-RAM", criterion: "RAM/stack within budget", critical_for_verdict: false },
      ],
    },
    transition_plan: { plan_id: "PLAN-MCUBOOT-S0-S2" },
    evidence: [
      ev("EV-PIN-MCUBOOT", "D01", "REPOSITORY", MCUBOOT_PINS.mcuboot),
      ev("EV-PARTITIONS-DTS", "D01", "STATIC_CONFIG", { boot_partition_size: 49152, slot0_address: 49152, slot0_size: 475136, slot1_address: 524288, slot1_size: 475136 }, ["build/zephyr/zephyr.dts"]),
      ev("EV-IMGTOOL-KEYTYPES", "D01", "STATIC_ANALYSIS", ["rsa-2048", "rsa-3072", "ecdsa-p256", "ecdsa-p384", "ed25519", "x25519"]),
      ev("EV-E11-BL-UPDATE", "E11", "STATIC_CONFIG", "UNSUPPORTED", ["build/zephyr/zephyr.dts"]),
      ev("EV-E01-BOOT", "E01", "EMULATED", "BOOT_OK", ["app_v1.signed.bin"]),
      ev("EV-E05-LAYOUT-S0", "E05", "STATIC_ARTIFACT", { signed_artifact_size: 36540, boot_slot_capacity: 475136 }, ["app_v1.signed.bin"]),
      ev("EV-E03-REJECT", "E03", "EMULATED", "REJECT", ["E03/uart.log"]),
      ev("EV-E02-PQC-SIGN", "E02", "SIGN_TOOL", { signing_result: "REJECTED", algorithm: "ml-dsa-65", tool: "imgtool 2.2.0", message: "'ml-dsa-65' is not one of 'rsa-2048', 'rsa-3072', 'ecdsa-p256', 'ecdsa-p384', 'ed25519', 'x25519'" }, ["E02/imgtool.log"]),
      ev("EV-X01-CROSS-KEY", "X01", "EMULATED", "REJECTED", ["X01/uart.log"]),
      ev("EV-E08-UPDATE", "E08", "EMULATED", "APPLIED"),
    ],
    evidence_gaps: [
      { gap_id: "GAP-E02-NO-CANDIDATE", requirement_id: "REQ-LAYOUT", gap_type: "NOT_EXECUTABLE", reason: "No post-quantum signed candidate image could be produced, so its size and boot cannot be measured", critical: true, requested_evidence: "E02 candidate image signed with ML-DSA" },
      { gap_id: "GAP-E12-SWAP-INTERRUPT", requirement_id: "INV-I4", gap_type: "UNKNOWN_FACT", reason: "Interrupted swap not observed; I4 remains UNKNOWN", critical: true, requested_evidence: "E12 interrupted swap with observed recovery" },
      { gap_id: "GAP-E07-RAM", requirement_id: "REQ-RAM", gap_type: "NOT_EXECUTABLE", reason: "Stack painting not run; linker region only", critical: false, requested_evidence: "E07 RAM/stack method beyond static linker region" },
    ],
  };
  const result: SemanticResult = {
    assessment_id: "MCUBOOT-LIVE",
    lifecycle: "COMPLETED",
    official: false,
    migration_verdict: "INCOMPATIBLE",
    candidate_verdict: "INCOMPATIBLE",
    transition_verdict: "INCOMPATIBLE",
    requirement_evaluation_results: [
      row("requirement_id", "REQ-PQC-SIGN", "TARGET", "STATE", "S2", "VIOLATED", true, ["EV-E02-PQC-SIGN", "EV-IMGTOOL-KEYTYPES"]),
      row("requirement_id", "REQ-BOOT-S0S1", "TRANSITION", "TRANSITION_STEP", "STEP-S0-S1", "VIOLATED", true, ["EV-E11-BL-UPDATE"]),
      row("requirement_id", "REQ-LAYOUT", "CURRENT", "STATE", "S0", "SATISFIED", true, ["EV-E05-LAYOUT-S0", "EV-PARTITIONS-DTS"]),
      row("requirement_id", "REQ-LAYOUT", "TARGET", "STATE", "S2", "UNKNOWN", true, [], ["GAP-E02-NO-CANDIDATE"]),
      row("requirement_id", "REQ-AUTH-NEGATIVE", "CURRENT", "STATE", "S0", "SATISFIED", false, ["EV-E03-REJECT", "EV-X01-CROSS-KEY"]),
      row("requirement_id", "REQ-RAM", "TARGET", "STATE", "S2", "UNKNOWN", false, [], ["GAP-E07-RAM"]),
    ],
    invariant_evaluation_results: [
      row("invariant_id", "INV-I1", "TRANSITION", "STATE", "S0", "SATISFIED", true, ["EV-E01-BOOT"]),
      row("invariant_id", "INV-I1", "TRANSITION", "STATE", "S2", "UNKNOWN", true, [], ["GAP-E02-NO-CANDIDATE"]),
      row("invariant_id", "INV-I4", "TRANSITION", "TRANSITION_STEP", "STEP-S0-S1", "UNKNOWN", true, [], ["GAP-E12-SWAP-INTERRUPT"]),
    ],
    explanation_graph: { nodes: [], edges: [] },
    findings: [],
    conditions: [],
    errors: [],
    canonical_hash: "sha256:7d3e91a0c4b25f86e1d07a9c3b4f5e6d7c8b9a0f1e2d3c4b5a69788796a5b4c3",
  };
  return { assessment, result };
}

const MCUBOOT_AI_PLAN: Omit<AIPlanView, "trace_ids"> = {
  status: "OK",
  message: "",
  blocked_templates: [],
  proposal: {
    summary:
      "MCUboot's update model differs from wolfBoot: the PQC signing attempt and the field-update capability decide the outcome. Added the signed v1 to v2 update so the deployed update path is shown to work before the negative checks are interpreted.",
    selected: [
      { template_id: "mcuboot.pqc_sign_attempt", priority: 1, rationale: "If the pinned imgtool cannot produce an ML-DSA image, the candidate state cannot exist on this toolchain." },
      { template_id: "mcuboot.bootloader_update_capability", priority: 2, rationale: "The default plan replaces MCUboot over the air; single-stage MCUboot normally cannot do this." },
      { template_id: "mcuboot.signed_update", priority: 3, rationale: "A positive control: shows that the update mechanism works, so the rejections in E03/X01 are meaningful." },
    ],
    skipped: [],
    suggested_new_tests: [],
  },
};

const MCUBOOT_AI_REPORT: Omit<AIReportView, "trace_ids"> = {
  status: "OK",
  message: "",
  report: {
    headline: "The pinned MCUboot toolchain cannot produce or verify ML-DSA images, and MCUboot cannot be replaced in the field.",
    verdict_echo: { migration: "INCOMPATIBLE", candidate: "INCOMPATIBLE", transition: "INCOMPATIBLE" },
    main_causes: [
      { text: "The pinned imgtool refused to create an ML-DSA key or signature; it only offers RSA, ECDSA, Ed25519 and X25519.", citations: ["REQ-PQC-SIGN", "EV-E02-PQC-SIGN", "EV-IMGTOOL-KEYTYPES"] },
      { text: "The built configuration is single-stage MCUboot with no bootloader slot, so deployed devices cannot receive a new bootloader over the air.", citations: ["REQ-BOOT-S0S1", "EV-E11-BL-UPDATE"] },
    ],
    verified: [
      { text: "The current ECDSA image boots and a valid update is applied.", citations: ["EV-E01-BOOT", "EV-E08-UPDATE"] },
      { text: "Tampered and wrongly keyed updates are rejected.", citations: ["EV-E03-REJECT", "EV-X01-CROSS-KEY"] },
    ],
    unknowns: [{ text: "Recovery from an interrupted swap was not observed.", citations: ["GAP-E12-SWAP-INTERRUPT"] }],
    executive_summary:
      "Unlike the wolfBoot profile, the candidate state itself is blocked here: the pinned MCUboot toolchain has no post-quantum signature support. Even with support, the deployed MCUboot cannot be replaced over the air.",
  },
};

const MCUBOOT_AI_ALTERNATIVES: Omit<AIAlternativesView, "trace_ids"> = {
  status: "OK",
  message: "",
  alternatives: {
    proposals: [
      {
        plan_id: "depot_reflash_mcuboot",
        title: "Re-flash MCUboot at a service depot",
        rationale: "Removes the field-update blocker (REQ-BOOT-S0S1). It does not add a post-quantum verifier, so the candidate stays blocked.",
        addresses: ["REQ-BOOT-S0S1"],
        preconditions: ["Devices can be returned to a depot"],
        tradeoffs: ["Logistics cost", "Does not solve REQ-PQC-SIGN"],
        evidence_still_needed: [],
      },
      {
        plan_id: "switch_to_wolfboot_depot",
        title: "Replace MCUboot with a PQC-capable bootloader (wolfBoot) at a depot",
        rationale: "wolfBoot supports ML-DSA on this chip. This is a different configuration and must be assessed with its own profile.",
        addresses: ["REQ-PQC-SIGN", "REQ-BOOT-S0S1"],
        preconditions: ["Depot re-flash", "Application re-linked for the wolfBoot layout"],
        tradeoffs: ["Bootloader family change", "Requalification"],
        evidence_still_needed: ["A full assessment on nRF52840 + wolfBoot"],
      },
      {
        plan_id: "mcuboot_lms_branch",
        title: "Adopt the upstream MCUboot LMS work (PR #2707)",
        rationale: "Hash-based LMS signatures would provide a post-quantum option inside MCUboot, but the work is not merged and runs in the simulator only.",
        addresses: ["REQ-PQC-SIGN"],
        preconditions: ["Upstream merge and a pinned release"],
        tradeoffs: ["Stateful signatures (key state management)"],
        evidence_still_needed: ["Build and boot on the pinned toolchain"],
      },
    ],
    not_addressable: [],
  },
};

// ------------------------------------------------------------------ scenario table

export function scenario(key: ScenarioKey, plan_id?: string): ScenarioSpec {
  switch (key) {
    case "wolfboot":
    case "wolfboot-hybrid": {
      const hybrid = key === "wolfboot-hybrid";
      return {
        key,
        configuration_id: "nrf52840-wolfboot-pqc",
        configuration_version: "1.0",
        change_id: "ecdsa_p256_to_mldsa87",
        plan_id: plan_id ?? (hybrid ? "staged_hybrid_dual_signature" : "bootloader_self_update"),
        mode: "LIVE",
        skipped: [],
        stageFinal: {},
        tests: wolfbootPlanTests(true, hybrid),
        stageLogs: {
          PREPARING: [
            ["runner", "profile nrf52840-wolfboot-pqc@1.0, ruleset 1.2, adapter wolfboot_v1_2"],
            ["runner", "workspace /data/runs/<run>/work (isolated, network disabled)"],
          ],
          AI_PLAN: [["runner", "AMD planner: 3 selected, 1 skipped, 1 blocked (not a registered test)"]],
          BUILD_SIGN: WOLFBOOT_BUILD_LOGS,
          EVALUATION: [
            ["runner", "adapter wolfboot_v1_2: 19 evidence rows, 4 gaps"],
            ["runner", "evaluate(): lifecycle COMPLETED"],
            ["runner", "manifest.json written"],
          ],
          NEXT_STEPS: [["runner", "explainer OK, alternatives OK"]],
        },
        artifacts: WOLFBOOT_ARTIFACTS,
        aiPlan: WOLFBOOT_AI_PLAN,
        aiReport: WOLFBOOT_AI_REPORT,
        aiAlternatives: WOLFBOOT_AI_ALTERNATIVES,
        doc: wolfbootDoc(),
        traces: [PLANNER_TRACE, EXPLAINER_TRACE, ALTERNATIVES_TRACE],
        source_pins: WOLFBOOT_PINS,
        tool_versions: WOLFBOOT_TOOLS,
        evidenceRun: "self",
      };
    }
    case "mcuboot":
      return {
        key,
        configuration_id: "nrf52840-mcuboot-pqc",
        configuration_version: "1.0",
        change_id: "ecdsa_p256_to_mldsa",
        plan_id: plan_id ?? "mcuboot_field_update",
        mode: "LIVE",
        skipped: [],
        stageFinal: {},
        tests: mcubootTests(),
        stageLogs: {
          PREPARING: [["runner", "profile nrf52840-mcuboot-pqc@1.0, ruleset 1.2, adapter mcuboot_v1_2"]],
          AI_PLAN: [["runner", "AMD planner: 3 selected, 0 skipped"]],
          BUILD_SIGN: MCUBOOT_BUILD_LOGS,
          EVALUATION: [["runner", "adapter mcuboot_v1_2: 10 evidence rows, 3 gaps"], ["runner", "evaluate(): lifecycle COMPLETED"]],
          NEXT_STEPS: [["runner", "explainer OK, alternatives OK"]],
        },
        artifacts: MCUBOOT_ARTIFACTS,
        aiPlan: MCUBOOT_AI_PLAN,
        aiReport: MCUBOOT_AI_REPORT,
        aiAlternatives: MCUBOOT_AI_ALTERNATIVES,
        doc: mcubootDoc(),
        traces: [PLANNER_TRACE, EXPLAINER_TRACE, ALTERNATIVES_TRACE],
        source_pins: MCUBOOT_PINS,
        tool_versions: MCUBOOT_TOOLS,
        evidenceRun: "self",
      };
    case "mcuboot-failed": {
      const tests = mcubootTests().map((x): MockTest => {
        if (x.planned_by === "AI_PLANNER") return { ...x, planned_by: "PROFILE_OPTIONAL" };
        return x;
      });
      const failedIdx = tests.findIndex((x) => x.template_id === "mcuboot.boot_current");
      tests[failedIdx] = {
        ...tests[failedIdx],
        outcome: "ERROR",
        failure_class: "BUILD_FAILED",
        observed: "west build exited with code 1 (MCUboot sysbuild)",
        duration_ms: 63110,
        stage: "BUILD_SIGN",
        observation_ids: [],
        logs: [
          ["build", "west build -b nrf52840dk/nrf52840 --sysbuild samples/releaseproof_app"],
          ["build", "CMake Error at /work/zephyr/cmake/modules/kconfig.cmake:396 (message):"],
          ["build", "  command failed with return code: 1"],
          ["build", "error: Aborting due to Kconfig warnings"],
          ["runner", "E01 ERROR: BUILD_FAILED"],
        ],
      };
      return {
        key,
        configuration_id: "nrf52840-mcuboot-pqc",
        configuration_version: "1.0",
        change_id: "ecdsa_p256_to_mldsa",
        plan_id: "mcuboot_field_update",
        mode: "LIVE",
        skipped: [],
        stageFinal: { AI_PLAN: { status: "INCONCLUSIVE", message: "AI_UNAVAILABLE" } },
        failAt: "BUILD_SIGN",
        failure: {
          failure_class: "BUILD_FAILED",
          message: "MCUboot sysbuild failed in the runner (Kconfig warnings treated as errors). No firmware was emulated.",
        },
        tests,
        stageLogs: {
          PREPARING: [["runner", "profile nrf52840-mcuboot-pqc@1.0"]],
          AI_PLAN: [
            ["runner", "AMD endpoint timeout after 20000 ms (attempt 2/2)"],
            ["runner", "AI_UNAVAILABLE: running required + all optional registered tests (PROFILE_OPTIONAL)"],
          ],
          BUILD_SIGN: MCUBOOT_BUILD_LOGS.slice(0, 3),
        },
        artifacts: [{ artifact_id: "art-build-log", name: "build.log", kind: "log", size_bytes: 48211, test_id: "E01", stage: "BUILD_SIGN" }],
        aiPlan: {
          status: "AI_UNAVAILABLE",
          message: "The AMD-hosted planner did not answer within the time budget. Fallback: required + all optional registered tests.",
          blocked_templates: [],
          proposal: null,
        },
        traces: [{ ...PLANNER_TRACE, latency_ms: 20000, prompt_tokens: 0, completion_tokens: 0, status: "AI_UNAVAILABLE", error: "ReadTimeout after 20000 ms" }],
        source_pins: MCUBOOT_PINS,
        tool_versions: MCUBOOT_TOOLS,
        evidenceRun: "self",
      };
    }
    case "reeval-reflash": {
      const doc = clone(CONDITIONAL);
      return {
        key,
        configuration_id: "nrf52840-wolfboot-pqc",
        configuration_version: "1.0",
        change_id: "ecdsa_p256_to_mldsa87",
        plan_id: plan_id ?? "field_service_reflash",
        mode: "REEVALUATION",
        skipped: ["AI_PLAN", "DISCOVERY", "BUILD_SIGN", "EMULATION_TESTS"],
        stageFinal: {},
        tests: [],
        stageLogs: {
          PREPARING: [["runner", "re-evaluation: loading observations of the parent LIVE run (no runner call)"]],
          EVALUATION: [["runner", "adapter wolfboot_v1_2 with plan field_service_reflash"], ["runner", "evaluate(): lifecycle COMPLETED"]],
          NEXT_STEPS: [["runner", "explainer OK; alternatives not requested"]],
        },
        artifacts: [{ artifact_id: "art-manifest", name: "manifest.json", kind: "manifest", size_bytes: 4210, test_id: null, stage: "EVALUATION" }],
        aiReport: {
          status: "OK",
          message: "",
          report: {
            headline: "With a field-service re-flash, no blocker remains. The plan depends on a controlled maintenance window.",
            verdict_echo: { migration: "CONDITIONAL", candidate: "COMPATIBLE", transition: "CONDITIONAL" },
            main_causes: [
              { text: "The bootloader is replaced by a technician, so the field self-update requirement no longer applies. The update must happen during a declared maintenance window, which is an open condition.", citations: ["REQ-MAINTENANCE-WINDOW", "GAP-REQ-MAINTENANCE-WINDOW-OPEN"] },
              { text: "The candidate ML-DSA image boots and fits, using evidence from the parent run.", citations: ["EV-E02-BOOT", "EV-E05-LAYOUT-G2"] },
            ],
            verified: [{ text: "Tampered image rejected.", citations: ["EV-E03-PANIC"] }],
            unknowns: [{ text: "RAM/stack budget not measured.", citations: ["GAP-E07-RAM"] }],
            executive_summary: "This re-evaluation reuses the parent run's measurements; nothing was re-executed. The decision changes because the delivery plan changes, not the evidence.",
          },
        },
        aiAlternatives: { status: "NOT_REQUESTED", message: "Alternatives are only drafted for the original plan.", alternatives: null },
        doc,
        traces: [EXPLAINER_TRACE],
        source_pins: WOLFBOOT_PINS,
        tool_versions: WOLFBOOT_TOOLS,
        evidenceRun: "parent",
      };
    }
    case "reeval-mcuboot": {
      const base = scenario("mcuboot");
      const doc = mcubootDoc();
      for (const r of doc.result.requirement_evaluation_results) {
        if (r.requirement_id === "REQ-BOOT-S0S1") {
          r.state = "OPEN_CONDITION";
          r.evidence_refs = [];
          r.gap_refs = ["GAP-DEPOT-LOGISTICS"];
        }
      }
      doc.assessment.evidence_gaps = [
        ...(doc.assessment.evidence_gaps ?? []),
        { gap_id: "GAP-DEPOT-LOGISTICS", requirement_id: "REQ-BOOT-S0S1", gap_type: "OPEN_CONDITION", reason: "Depot return and re-flash procedure is declared, not observed", critical: true, requested_evidence: "Signed depot procedure" },
      ];
      doc.result.transition_verdict = "INCOMPATIBLE";
      doc.result.canonical_hash = "sha256:2b8c4d6e0f1a3c5e7092b4d6f8a0c2e4f6a8b0d2e4f6081a3c5e7f9b1d3f5a7c";
      return {
        ...base,
        key,
        plan_id: plan_id ?? "depot_reflash_mcuboot",
        mode: "REEVALUATION",
        skipped: ["AI_PLAN", "DISCOVERY", "BUILD_SIGN", "EMULATION_TESTS"],
        tests: [],
        stageLogs: {
          PREPARING: [["runner", "re-evaluation: loading observations of the parent LIVE run (no runner call)"]],
          EVALUATION: [["runner", "adapter mcuboot_v1_2 with plan depot_reflash_mcuboot"], ["runner", "evaluate(): lifecycle COMPLETED"]],
        },
        artifacts: [{ artifact_id: "art-manifest", name: "manifest.json", kind: "manifest", size_bytes: 4012, test_id: null, stage: "EVALUATION" }],
        aiPlan: undefined,
        aiReport: {
          status: "OK",
          message: "",
          report: {
            headline: "Depot re-flash removes the field-update blocker, but the candidate is still blocked by missing ML-DSA support.",
            verdict_echo: { migration: "INCOMPATIBLE", candidate: "INCOMPATIBLE", transition: "INCOMPATIBLE" },
            main_causes: [{ text: "The pinned imgtool still cannot produce an ML-DSA signature, so no candidate image exists.", citations: ["REQ-PQC-SIGN", "EV-E02-PQC-SIGN"] }],
            verified: [],
            unknowns: [{ text: "Depot logistics are declared, not observed.", citations: ["GAP-DEPOT-LOGISTICS"] }],
            executive_summary: "Changing how the bootloader is delivered does not change what the toolchain can sign.",
          },
        },
        aiAlternatives: { status: "NOT_REQUESTED", message: "Alternatives are only drafted for the original plan.", alternatives: null },
        doc,
        traces: [EXPLAINER_TRACE],
        evidenceRun: "parent",
      };
    }
    case "reference": {
      const doc = clone(WP0);
      return {
        key,
        configuration_id: "nrf52840-wolfboot-pqc",
        configuration_version: "wp0-freeze-20261001",
        change_id: "ecdsa_p256_to_mldsa87",
        plan_id: "PLAN-WP0-S0-S2",
        mode: "REFERENCE",
        skipped: ["AI_PLAN", "NEXT_STEPS"],
        stageFinal: {},
        tests: wolfbootPlanTests(false, true).map((x) => ({ ...x, planned_by: "POLICY_REQUIRED" })),
        stageLogs: {},
        artifacts: WOLFBOOT_ARTIFACTS,
        doc,
        traces: [],
        source_pins: { wolfboot: WOLFBOOT_PINS.wolfboot, wolfcrypt: WOLFBOOT_PINS.wolfcrypt },
        tool_versions: { renode: "1.16.1", "arm-none-eabi-gcc": "14.2.rel1" },
        evidenceRun: "keep",
      };
    }
  }
}

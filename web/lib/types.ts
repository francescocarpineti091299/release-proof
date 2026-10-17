/**
 * Hand-written mirrors of the backend contracts. Field names are exact.
 *  - backend/releaseproof/contracts/runner.py   (enums, events, Observation)
 *  - backend/releaseproof/contracts/api.py      (view models)
 *  - backend/releaseproof/contracts/ai.py       (structured AI outputs)
 *  - backend/releaseproof/contracts/profile.py  (configuration registry)
 */

// ------------------------------------------------------------------ runner.py

export type Stage =
  | "PREPARING"
  | "DISCOVERY"
  | "AI_PLAN"
  | "BUILD_SIGN"
  | "EMULATION_TESTS"
  | "EVALUATION"
  | "NEXT_STEPS";

/** Display order of stages shown to users (WORKSTREAMS.md). */
export const STAGE_ORDER: Stage[] = [
  "PREPARING",
  "AI_PLAN",
  "DISCOVERY",
  "BUILD_SIGN",
  "EMULATION_TESTS",
  "EVALUATION",
  "NEXT_STEPS",
];

export type StageStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "INCONCLUSIVE" | "SKIPPED";

export type FailureClass =
  | "ENVIRONMENT_SETUP"
  | "BUILD_FAILED"
  | "TOOL_FAILURE"
  | "TIMEOUT"
  | "INCONCLUSIVE"
  | "INTERNAL"
  | "AI_UNAVAILABLE";

export type Origin = "MEASURED_TOOL" | "OBSERVED_EMULATION" | "DECLARED" | "AI_PROPOSAL";

export type TestOutcome = "PASS" | "FAIL" | "INCONCLUSIVE" | "NOT_EXECUTED" | "ERROR";

export type LogStream = "build" | "sign" | "renode" | "uart" | "tool" | "runner";

export type ArtifactKind =
  | "elf"
  | "bin"
  | "signed_image"
  | "log"
  | "uart"
  | "script"
  | "config"
  | "manifest"
  | "other";

export type ObservationSubject =
  | "deployed_state"
  | "candidate_state"
  | "transition"
  | "platform"
  | "toolchain";

export interface Observation {
  observation_id: string;
  test_id: string;
  subject: ObservationSubject;
  fact: string;
  value: unknown;
  unit?: string | null;
  origin: Origin;
  acquisition_mode: string;
  source_artifact_ids: string[];
  locator?: string | null;
  parser: string;
}

interface EventBase {
  seq: number;
  ts: string;
  run_id: string;
}

export interface StageEvent extends EventBase {
  type: "stage";
  stage: Stage;
  status: StageStatus;
  message: string;
}

export interface LogEvent extends EventBase {
  type: "log";
  stream: LogStream;
  line: string;
  test_id?: string | null;
}

export interface ArtifactEvent extends EventBase {
  type: "artifact";
  artifact_id: string;
  name: string;
  path: string;
  sha256: string;
  size_bytes: number;
  kind: ArtifactKind;
  test_id?: string | null;
}

export interface ObservationEvent extends EventBase {
  type: "observation";
  observation: Observation;
}

export interface TestResultEvent extends EventBase {
  type: "test_result";
  test_id: string;
  template_id: string;
  outcome: TestOutcome;
  expected: string;
  observed: string;
  duration_ms: number;
  observation_ids: string[];
  failure_class?: FailureClass | null;
}

export interface ErrorEvent extends EventBase {
  type: "error";
  failure_class: FailureClass;
  message: string;
  test_id?: string | null;
}

export interface DoneEvent extends EventBase {
  type: "done";
  status: "SUCCEEDED" | "FAILED";
  summary: string;
  tool_versions: Record<string, string>;
  source_pins: Record<string, string>;
}

// ------------------------------------------------------------------ ai.py

export interface PlannedTemplate {
  template_id: string;
  priority: number;
  rationale: string;
}

export interface SkippedTemplate {
  template_id: string;
  reason: string;
}

export interface SuggestedTest {
  title: string;
  purpose: string;
}

export interface TestPlanProposal {
  selected: PlannedTemplate[];
  skipped: SkippedTemplate[];
  suggested_new_tests: SuggestedTest[];
  summary: string;
}

export interface CitedStatement {
  text: string;
  citations: string[];
}

export interface NarrativeReport {
  headline: string;
  verdict_echo: Partial<Record<"migration" | "candidate" | "transition", string | null>>;
  main_causes: CitedStatement[];
  verified: CitedStatement[];
  unknowns: CitedStatement[];
  executive_summary: string;
}

export interface ChangeProposal {
  plan_id: string;
  title: string;
  rationale: string;
  addresses: string[];
  preconditions: string[];
  tradeoffs: string[];
  evidence_still_needed: string[];
}

export interface AlternativesProposal {
  proposals: ChangeProposal[];
  not_addressable: string[];
}

// ------------------------------------------------------------------ profile.py

export type ProfileStatus = "SUPPORTED" | "EXPERIMENTAL" | "UNAVAILABLE";

export interface Board {
  id: string;
  name: string;
  soc: string;
  emulator: "renode";
  platform_script: string;
}

export interface Bootloader {
  family: "wolfboot" | "mcuboot";
  name: string;
  repo: string;
  commit: string;
  version_label: string;
  license: string;
}

export interface AlternativePlan {
  plan_id: string;
  title: string;
  description: string;
  mechanism: string;
  requires_rerun_tests: boolean;
  status: "EXECUTABLE" | "REQUIRES_EXTERNAL_VALIDATION";
}

export interface ChangeScenario {
  change_id: string;
  title: string;
  summary: string;
  from_scheme: string;
  to_scheme: string;
  default_plan_id: string;
  default_plan_title: string;
  required_templates: string[];
  optional_templates: string[];
  alternatives: AlternativePlan[];
}

export interface Runner {
  service: string;
  image: string;
  timeout_seconds: number;
}

export interface Profile {
  id: string;
  version: string;
  status: ProfileStatus;
  title: string;
  description: string;
  board: Board;
  bootloader: Bootloader;
  toolchain: Record<string, string>;
  runner: Runner;
  changes: ChangeScenario[];
  assessment_adapter: string;
  ruleset_version: "1.2";
  known_limitations: string[];
}

export interface TestTemplate {
  template_id: string;
  test_id: string;
  family: "wolfboot" | "mcuboot";
  title: string;
  description: string;
  negative: boolean;
  expected: string;
  params_schema: Record<string, unknown>;
  est_seconds: number;
}

export interface TestCatalog {
  version: string;
  tests: Record<string, string>;
  templates: TestTemplate[];
}

// ------------------------------------------------------------------ api.py

export type RunStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
export type RunMode = "LIVE" | "REEVALUATION" | "REFERENCE";
export type AIStatus =
  | "OK"
  | "SCHEMA_INVALID"
  | "REJECTED_BY_GUARDRAIL"
  | "AI_UNAVAILABLE"
  | "NOT_REQUESTED";

export type PlannedBy = "POLICY_REQUIRED" | "AI_PLANNER" | "PROFILE_OPTIONAL";

export interface RunCreate {
  configuration_id: string;
  change_id: string;
  plan_id?: string | null;
  idempotency_key?: string | null;
}

export interface StageView {
  stage: Stage;
  status: StageStatus;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  message: string;
}

export interface TestResultView {
  test_id: string;
  template_id: string;
  title: string;
  negative: boolean;
  outcome: TestOutcome;
  expected: string;
  observed: string;
  duration_ms: number;
  observation_ids: string[];
  failure_class?: FailureClass | null;
  planned_by: PlannedBy;
}

export type Verdict = "COMPATIBLE" | "CONDITIONAL" | "INDETERMINATE" | "INCOMPATIBLE";

export interface VerdictView {
  lifecycle: string;
  migration: string | null;
  candidate: string | null;
  transition: string | null;
  canonical_hash: string | null;
  official: false;
}

export interface FailureView {
  failure_class: FailureClass;
  message: string;
}

export interface AIArtifact {
  status: AIStatus;
  trace_ids: string[];
  message: string;
}

export interface AIPlanView extends AIArtifact {
  proposal?: TestPlanProposal | null;
  blocked_templates: string[];
}

export interface AIReportView extends AIArtifact {
  report?: NarrativeReport | null;
}

export interface AIAlternativesView extends AIArtifact {
  alternatives?: AlternativesProposal | null;
}

export interface RunView {
  run_id: string;
  mode: RunMode;
  status: RunStatus;
  configuration_id: string;
  configuration_version: string;
  change_id: string;
  plan_id: string;
  parent_run_id?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  queue_position?: number | null;
  stages: StageView[];
  tests: TestResultView[];
  verdict?: VerdictView | null;
  failure?: FailureView | null;
  ai_plan?: AIPlanView | null;
  ai_report?: AIReportView | null;
  ai_alternatives?: AIAlternativesView | null;
  source_pins: Record<string, string>;
  tool_versions: Record<string, string>;
}

export interface ArtifactView {
  artifact_id: string;
  name: string;
  kind: string;
  sha256: string;
  size_bytes: number;
  test_id?: string | null;
  url: string;
}

export interface EvidenceView {
  id: string;
  test_id: string | null;
  value: unknown;
  evidence_kind: string;
  acquisition_mode: string;
  origin: string;
  run_id: string | null;
  artifacts: ArtifactView[];
  locator?: string | null;
}

export interface ResultView {
  run_id: string;
  /** V1.2 assessment document evaluated. */
  assessment: AssessmentDoc;
  /** SemanticAssessmentResult (contract V1.2). */
  result: SemanticResult;
  gap_plan?: Record<string, unknown> | unknown[] | null;
  dossier_markdown?: string | null;
  evidence: EvidenceView[];
  manifest_sha256: string;
}

export type AIModule = "planner" | "explainer" | "alternatives" | "assistant" | "smoke";

export interface AITraceView {
  trace_id: string;
  run_id: string | null;
  module: AIModule;
  provider: string;
  model: string;
  endpoint_host: string;
  hardware_label: string;
  request_id: string | null;
  prompt_template: string;
  started_at: string;
  latency_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  status: AIStatus;
  error?: string | null;
}

export interface AssistantMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AssistantRequest {
  run_id: string;
  messages: AssistantMessage[];
}

export type SSEType =
  | "stage"
  | "log"
  | "artifact"
  | "observation"
  | "test_result"
  | "error"
  | "done"
  | "run"
  | "ai";

export interface SSEEvent {
  id: number;
  type: SSEType;
  data: Record<string, unknown>;
}

// ------------------------------------------------------------------ V1.2 result documents
// The API exposes these as dict[str, Any]; only the fields the UI reads are typed.

export type RequirementState = "SATISFIED" | "VIOLATED" | "UNKNOWN" | "OPEN_CONDITION";

export interface EvaluationRow {
  requirement_id?: string;
  invariant_id?: string;
  phase: string;
  subject_type: string;
  subject_ref: string;
  state: RequirementState | string;
  critical_for_verdict: boolean;
  evidence_refs: string[];
  gap_refs: string[];
  rule_refs: string[];
  provenance?: string;
  findings?: { requirement_id?: string; observation?: string }[];
}

export interface SemanticResult {
  assessment_id: string;
  lifecycle: string;
  official: boolean;
  migration_verdict: Verdict | null;
  candidate_verdict: Verdict | null;
  transition_verdict: Verdict | null;
  requirement_evaluation_results: EvaluationRow[];
  invariant_evaluation_results: EvaluationRow[];
  explanation_graph?: Record<string, unknown>;
  findings: Record<string, unknown>[];
  conditions: {
    condition_id?: string;
    step_id?: string;
    requirement_id?: string;
    allowed_by_profile?: boolean;
  }[];
  errors: string[];
  canonical_hash: string | null;
  [key: string]: unknown;
}

export interface EvidenceGap {
  gap_id: string;
  requirement_id?: string;
  gap_type?: string;
  reason?: string;
  critical?: boolean;
  requested_evidence?: string;
}

export interface AssessmentDoc {
  assessment_id?: string;
  contract_version?: string;
  created_at?: string;
  profile?: {
    id?: string;
    requirements?: { id: string; criterion?: string; risk_category?: string; critical_for_verdict?: boolean }[];
    [key: string]: unknown;
  };
  transition_plan?: { plan_id?: string; [key: string]: unknown };
  evidence?: Record<string, unknown>[];
  evidence_gaps?: EvidenceGap[];
  [key: string]: unknown;
}

// ------------------------------------------------------------------ endpoints beyond contracts/api.py (real backend, WS-C)

/** GET /api/configurations item. */
export interface TemplateView {
  template_id: string;
  test_id: string;
  title: string;
  description: string;
  negative: boolean;
  expected: string;
  est_seconds: number;
  required: boolean;
}

export interface ChangeView {
  change_id: string;
  title: string;
  summary: string;
  from_scheme: string;
  to_scheme: string;
  default_plan_id: string;
  default_plan_title: string;
  templates: TemplateView[];
  alternatives: AlternativePlan[];
  est_seconds_total: number;
}

export interface ConfigurationView {
  id: string;
  version: string;
  status: ProfileStatus | string;
  title: string;
  description: string;
  board: Board;
  bootloader: Bootloader;
  toolchain: Record<string, string>;
  runner_image: string;
  timeout_seconds: number;
  ruleset_version: string;
  known_limitations: string[];
  changes: ChangeView[];
}

/** GET /api/assessments/{id}/plan item. */
export interface PlannedTestView {
  template_id: string;
  test_id: string;
  planned_by: PlannedBy;
  title: string;
  negative: boolean;
  est_seconds: number;
  params?: Record<string, unknown>;
}

/** GET /api/reference */
export interface ReferenceView {
  recorded?: true;
  recorded_at: string;
  notice: string;
  canonical_hash: string | null;
  run: RunView;
  result: ResultView | null;
}

/** GET /api/amd */
export interface AmdProviderInfo {
  provider: string;
  hardware: string;
  endpoint_host: string;
  configured: boolean;
  unavailable_reason?: string | null;
  models: Record<string, string | null>;
  prompt_templates: Record<string, string>;
  allowed_hosts: string[];
  response_format?: string;
  fallback_provider: string | null;
}

export interface AmdTraceStats {
  count: number;
  ok: number;
  ok_rate: number | null;
  latency_ms_p50: number | null;
  latency_ms_p95: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  by_module: Record<string, number>;
}

export interface AmdView {
  provider: AmdProviderInfo;
  traces: AmdTraceStats;
}

export interface AmdModuleStats {
  module: AIModule | string;
  model: string | null;
  calls: number;
  ok_rate: number | null;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
}

/** What the /amd page renders: the API view plus recent traces gathered from recent runs. */
export interface AmdDashboard {
  view: AmdView;
  per_module: AmdModuleStats[];
  recent_traces: AITraceView[];
}

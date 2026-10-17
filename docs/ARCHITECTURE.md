# ReleaseProof — Architecture

```mermaid
flowchart LR
  subgraph Browser
    UI[Next.js UI<br/>wizard · live run · evidence · alternatives]
  end
  subgraph AWS EC2 c7a (AMD EPYC)
    C[Caddy TLS] --> UI2[web :3000]
    C --> API[FastAPI :8000<br/>orchestrator · SQLite · artifacts]
    API -->|NDJSON /execute| RW[runner-wolfboot<br/>wolfBoot · Arm GCC · Renode]
    API -->|NDJSON /execute| RM[runner-mcuboot<br/>Zephyr · MCUboot · imgtool · Renode]
    API --> AD[Assessment adapters] --> ENG[V1.2 semantic engine<br/>validate · evaluate · canonical hash]
  end
  API -->|OpenAI-compatible, allow-listed host| AMD[(LLM on AMD Instinct<br/>AMD Developer Cloud)]
  UI --> C
```

## Responsibilities

| Component | Does | Never does |
|---|---|---|
| Runners | Build, sign, emulate (Renode), parse UART/artifacts, emit typed **observations** with artifact hashes | Decide verdicts; run arbitrary commands (allow-listed templates only); reach the internet |
| Adapters | Project observations into a V1.2 assessment (states, plan, evidence, gaps) | Invent facts: missing observation ⇒ `UNKNOWN`/gap |
| Engine (`core/`) | Deterministic verdicts (candidate / transition / migration), explanation graph, canonical hash | Change without golden-hash regression |
| AI gateway (AMD) | Test planning within the catalog, cited explanations, alternative plans from an allowed set, grounded chat | Produce verdicts, measurements or shell commands; fall back to non-AMD providers |
| Orchestrator | State machine, queue, persistence, SSE, manifests, re-evaluation runs | Fall back to recorded data when a runner fails |

## Run lifecycle

`PREPARING → AI_PLAN → DISCOVERY → BUILD_SIGN → EMULATION_TESTS → EVALUATION → NEXT_STEPS`

- **AI_PLAN**: the AMD-hosted model orders/selects optional templates; required templates are
  enforced by policy; unknown templates are blocked and shown.
- **Runner**: one isolated workspace per run, pinned sources baked in the image, ephemeral keys,
  Renode virtual time, UART captured to file, every artifact hashed.
- **EVALUATION**: adapter → `evaluate()` → gap plan → dossier → `manifest.json` (inputs, pins,
  artifact hashes, result hash).
- **NEXT_STEPS**: cited explanation + alternative plans (PROPOSAL). Choosing an alternative creates a
  **new** run (`REEVALUATION` on the parent's evidence, or `LIVE` when new tests are needed). History
  is never mutated.

## Trust boundaries

- LLM output is untrusted: JSON-schema validation, allow-lists, citation checks, verdict echo check.
- Tool output (logs/UART) passed to the LLM is wrapped as untrusted data (prompt-injection defense).
- Runner network is `internal`; secrets only in the API container.

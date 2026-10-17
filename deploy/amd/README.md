# AMD inference for ReleaseProof

Every ReleaseProof LLM call (planner, explainer, alternatives, assistant) goes to **one
OpenAI-compatible endpoint running on AMD hardware**. There is no fallback provider: if the AMD
endpoint is missing, not allow-listed or failing, the AI steps report `AI_UNAVAILABLE` and the
deterministic pipeline continues without them.

## Managed API: AMD Token Factory / AMD Developer Cloud (default)

```bash
AMD_LLM_BASE_URL=https://developer.amd.com.cn/radeon/api/v1   # from the model card
AMD_LLM_API_KEY=<copy the exact key from Token Factory>    # server side only
AMD_LLM_MODEL=Gemma-4-31B-IT
AMD_LLM_ALLOWED_HOSTS=developer.amd.com.cn
AMD_LLM_PROVIDER_LABEL="AMD Token Factory"
AMD_LLM_HARDWARE_LABEL="AMD-hosted (GPU not disclosed)"
AMD_LLM_RESPONSE_FORMAT=json_object
```

The repository's `.env.example` contains this preset without a key. Copy it to `.env` and
set `AMD_LLM_API_KEY`. Docker Compose passes it only to the API, not the browser or runners.
Keys are case-sensitive: AMD documents a lowercase `rc-` prefix followed by 48 hexadecimal
characters. A copied `Rc-` prefix can be rejected by the upstream LLMGateway even when
`GET /models` succeeds. Check the prefix against the dashboard before requesting a new key.
Do not lowercase arbitrary provider keys or modify their secret suffix.
Rotate any key shared in chat or logs. The catalog does not identify the GPU per shared model,
so only replace the hardware label with a specific GPU when AMD provides that evidence.

### Shared model IDs

Set `AMD_LLM_MODEL` to any of these IDs, or use the existing per-module overrides:

| Model ID | Input | Context |
|---|---|---|
| `DeepSeek-V4.1-Flash` | Text + images | 1,048,576 |
| `DeepSeek-V4-Flash` | Text | 1,048,576 |
| `DeepSeek-V4-Flash-Vision-Exp` | Text + images | 1,048,576 |
| `MiMo-V2.6-Flash` | Text + images | 1,048,576 |
| `Qwen3.8-Flash-Next` | Text + images | 262,144 |
| `Qwen3.8-27B` | Text + images | 262,144 |
| `Gemma-4-31B-IT` | Text + images | 262,144 |
| `GLM-5.3-Flash` | Text | 262,144 |
| `MiniCPM-V-4.7-35B-A3B` | Text + images | 262,144 |
| `MiniCPM-V-4.7-1B` | Text + images | 262,144 |
| `MiniCPM5-2B` | Text | 131,072 |

IDs and capabilities were checked against `GET /models` on 2026-10-17; availability may change.
ReleaseProof currently sends **text only**, even when the selected model supports images.
The existing context budget remains bounded; a large model window does not send more data.

`Gemma-4-31B-IT` (Google Gemma served on AMD) is the default for all four modules. In a
2-iteration Token Factory comparison
(`docs/AMD_BENCHMARK_PRIOR_20261017T133903Z.json`) it produced 12 OK / 2 timeout traces with a
schema-valid rate of 1.0, against 0.75 for `DeepSeek-V4-Flash`. That is a small sample, not a
full benchmark. The Gemma smoke `docs/AMD_SMOKE_GEMMA.json` records 10/10 logical calls OK,
and the strict live acceptance `docs/acceptance/20261017T154930Z.json` passes both profiles with
Gemma. It answers directly when reasoning is omitted. For Qwen/GLM, the shared API may enable
long reasoning by default. Use
`AMD_LLM_EXTRA_BODY='{"reasoning_effort":"low"}'` and benchmark the token budgets before switching.
`chat_template_kwargs.enable_thinking` is **not forwarded by the shared gateway**; it is only
appropriate for dedicated vLLM/SGLang endpoints. All models still pass through local schema,
citation and verdict guardrails; the LLM never decides the engineering verdict.

The shared preset uses `json_object`: live strict `json_schema` requests to DeepSeek produced
upstream 504 errors wrapped in HTTP 500, while JSON mode completed a schema-valid planner call.
This changes only server-side generation constraints, not local validation or the verdict
engine. Use `auto`/`json_schema` for dedicated endpoints that reliably support strict schemas.
Transient upstream timeouts also occasionally occur in JSON mode. The client retries once
when HTTP 500 explicitly reports `call_upstream_timeout`, just as for HTTP 502/503/504.
Arbitrary 500s, authentication errors and quota errors are not retried; there is no provider
fallback, and persistent failures still report `AI_UNAVAILABLE` without changing verdicts.

API reference: [chat completions](https://amd-aim.github.io/radeon-cloud-docs/api/chat-completions/).

## Self-hosted: vLLM on an AMD Developer Cloud MI300X droplet

Use this for a dedicated endpoint with ROCm, for example when Token Factory quota is exhausted.

1. Create an MI300X GPU droplet on AMD Developer Cloud (ROCm image with Docker preinstalled).
2. Copy `vllm_mi300x.sh` to the droplet and run it:

   ```bash
   export VLLM_API_KEY=$(openssl rand -hex 24)   # keep it; it goes into AMD_LLM_API_KEY
   export HF_TOKEN=hf_...                         # only for gated models
   MODEL=Qwen/Qwen3-32B REASONING_PARSER=qwen3 ./vllm_mi300x.sh
   ```

   The script runs `vllm/vllm-openai-rocm` with `/dev/kfd` and `/dev/dri`, `--ipc=host`,
   `video`/`render` groups, `seccomp=unconfined`, `--enable-auto-tool-choice` and structured
   outputs (`--structured-outputs-config.backend auto`). vLLM requires the Bearer key
   (`VLLM_API_KEY`). Pin `IMAGE=vllm/vllm-openai-rocm:<tag>` once you have a working tag. Older vLLM
   versions use `--guided-decoding-backend` instead of `--structured-outputs-config.backend`: pass
   it through `EXTRA_ARGS` and set `STRUCTURED_BACKEND` accordingly (or edit the script).
3. Check from your laptop:

   ```bash
   curl -H "Authorization: Bearer $VLLM_API_KEY" http://<droplet-ip>:8000/v1/models
   ```

4. Lock the port down to the ReleaseProof API host (EC2 Elastic IP) with the droplet firewall
   (`ufw allow from <eip> to any port 8000`). The Bearer key goes over plain HTTP unless you put
   TLS in front: a Caddy reverse proxy on the droplet with a hostname such as
   `<droplet-ip>.sslip.io` takes two lines.
5. Configure ReleaseProof:

   ```bash
   AMD_LLM_BASE_URL=https://<droplet-ip>.sslip.io/v1    # or http://<droplet-ip>:8000/v1
   AMD_LLM_API_KEY=$VLLM_API_KEY
   AMD_LLM_MODEL=Qwen/Qwen3-32B                         # = --served-model-name
   AMD_LLM_ALLOWED_HOSTS=<droplet-ip>.sslip.io          # or <droplet-ip>
   AMD_LLM_PROVIDER_LABEL="AMD Developer Cloud (vLLM)"
   AMD_LLM_HARDWARE_LABEL="AMD Instinct MI300X"
   # Qwen3 thinking off for faster, shorter JSON:
   AMD_LLM_EXTRA_BODY='{"chat_template_kwargs":{"enable_thinking":false}}'
   ```

6. Record evidence: `rocm-smi` output, `docker logs releaseproof-vllm | head`, then run
   `scripts/amd_smoke.py` and `scripts/amd_benchmark.py` (see below).

### Model choice on one MI300X (192 GB HBM3)

| Model | Notes |
|---|---|
| `Qwen/Qwen3-32B` | Default. Good JSON fidelity; `TOOL_PARSER=hermes`, `REASONING_PARSER=qwen3`. |
| `google/gemma-3-27b-it` (or a newer Gemma instruct model) | **Google prize option** (Gemma on AMD). Gated: accept the license on Hugging Face and set `HF_TOKEN`. Use the tool parser your vLLM version documents for Gemma (e.g. `TOOL_PARSER=pythonic`); ReleaseProof does not need tool calls, it uses structured outputs. |
| `meta-llama/Llama-3.3-70B-Instruct` | Fits with bf16 on one MI300X; slower. `TOOL_PARSER=llama3_json`. |

Choose the model with `scripts/amd_benchmark.py --models A,B` (schema validity, citation and
verdict-echo fidelity, latency, prompt-injection resistance). Per-module overrides
(`AMD_LLM_MODEL_PLANNER`, `..._EXPLAINER`, `..._ALTERNATIVES`, `..._ASSISTANT`) let you run, for
example, Gemma for the assistant and Qwen for the explainer. Both must be served on AMD.

## Smoke and benchmark

From the repo root, using your local `.env` (or omit `--env-file` for exported variables):

```powershell
backend\.venv\Scripts\python.exe scripts\amd_smoke.py --env-file .env
backend\.venv\Scripts\python.exe scripts\amd_benchmark.py --env-file .env -n 5
```

Exported environment variables take precedence over the file. No dotenv file is discovered
automatically, so tests/CI do not pick up local credentials. Reports go to `docs/AMD_SMOKE.json`
and `docs/AMD_BENCHMARK.json`. These commands make real, potentially billable inference calls.
A successful `GET /models` alone does not prove inference authentication; the smoke test must
complete real chat requests. HTTP 401 means the key was rejected; HTTP 429 means quota/rate limit.

Benchmark iterations must be positive. Exit codes: `0` all logical calls OK with no detected
injection leak or verdict-falsification obedience, `1` some calls not OK or an adversarial
check failed, `2` endpoint
unavailable for every call. The JSON files contain traces (model, endpoint host, request id,
latency, tokens, status, prompt template version). They never contain the API key.

The retained `docs/AMD_SMOKE_TOKEN_FACTORY.json` records 9/10 successful logical calls and
one upstream outage with the previous default `DeepSeek-V4-Flash`; it is not a completed
benchmark and is not Gemma evidence. The Gemma smoke is `docs/AMD_SMOKE_GEMMA.json` (10/10 OK). `docs/AMD_BENCHMARK.json` is a generated
output, currently absent from version control. Do not report a schema-valid benchmark rate or
specific managed GPU identity from the smoke alone.

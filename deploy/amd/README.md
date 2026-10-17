# AMD inference for ReleaseProof

Every ReleaseProof LLM call (planner, explainer, alternatives, assistant) goes to **one
OpenAI-compatible endpoint running on AMD hardware**. There is no fallback provider: if the AMD
endpoint is missing, not allow-listed or failing, the AI steps report `AI_UNAVAILABLE` and the
deterministic pipeline continues without them.

## Plan A: AMD Token Factory / AMD Developer Cloud managed API

```bash
AMD_LLM_BASE_URL=https://developer.amd.com.cn/radeon/api/v1   # from the model card
AMD_LLM_API_KEY=rc-...                                         # server side only
AMD_LLM_MODEL=<model id from the card or GET /models>
AMD_LLM_ALLOWED_HOSTS=developer.amd.com.cn
AMD_LLM_PROVIDER_LABEL="AMD Token Factory"
AMD_LLM_HARDWARE_LABEL="<GPU shown on the model card>"
```

## Plan B: self-hosted vLLM on an AMD Developer Cloud MI300X droplet

Use this if Token Factory has no quota or no suitable model.

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

From the repo root, with the variables above exported:

```powershell
backend\.venv\Scripts\python.exe scripts\amd_smoke.py              # 10 calls -> docs/AMD_SMOKE.json
backend\.venv\Scripts\python.exe scripts\amd_benchmark.py -n 5     # -> docs/AMD_BENCHMARK.json
```

Exit codes: `0` all OK, `1` some calls not OK (or a prompt injection leaked), `2` endpoint
unavailable for every call. The JSON files contain traces (model, endpoint host, request id,
latency, tokens, status, prompt template version). They never contain the API key.

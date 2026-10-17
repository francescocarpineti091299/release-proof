#!/usr/bin/env bash
# Self-hosted ReleaseProof AI: serve an open-weight model with vLLM (ROCm) on an AMD Developer Cloud
# MI300X droplet and expose an OpenAI-compatible endpoint. Run ON THE DROPLET.
#
#   export VLLM_API_KEY=$(openssl rand -hex 24)   # the key ReleaseProof will send as Bearer token
#   export HF_TOKEN=hf_...                         # needed for gated models (e.g. Gemma)
#   MODEL=Qwen/Qwen3-32B ./vllm_mi300x.sh
#
# Variables (all optional except VLLM_API_KEY):
#   MODEL               Hugging Face model id            (default Qwen/Qwen3-32B)
#   SERVED_NAME         name clients send in "model"     (default = MODEL)
#   IMAGE               vLLM ROCm image                  (default vllm/vllm-openai-rocm:latest; pin a tag)
#   PORT                host port                        (default 8000)
#   TP                  tensor parallel size (GPUs)      (default 1; one MI300X has 192 GB HBM3)
#   MAX_MODEL_LEN       context length                   (default 32768)
#   TOOL_PARSER         --tool-call-parser               (default hermes; Gemma: see README)
#   REASONING_PARSER    --reasoning-parser, empty = off  (default empty; Qwen3: qwen3)
#   STRUCTURED_BACKEND  structured-outputs backend       (default auto: xgrammar/guidance)
#   EXTRA_ARGS          appended verbatim to vllm serve
set -euo pipefail

: "${VLLM_API_KEY:?set VLLM_API_KEY (never commit it)}"
MODEL="${MODEL:-Qwen/Qwen3-32B}"
SERVED_NAME="${SERVED_NAME:-$MODEL}"
IMAGE="${IMAGE:-vllm/vllm-openai-rocm:latest}"
PORT="${PORT:-8000}"
TP="${TP:-1}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-32768}"
TOOL_PARSER="${TOOL_PARSER:-hermes}"
REASONING_PARSER="${REASONING_PARSER:-}"
STRUCTURED_BACKEND="${STRUCTURED_BACKEND:-auto}"
NAME="${NAME:-releaseproof-vllm}"
HF_CACHE="${HF_CACHE:-$HOME/.cache/huggingface}"

# Sanity: this must be an AMD GPU host.
if ! ls /dev/kfd >/dev/null 2>&1; then
  echo "ERROR: /dev/kfd not found - this is not a ROCm/AMD GPU host" >&2
  exit 1
fi
command -v rocm-smi >/dev/null 2>&1 && rocm-smi --showproductname || true

mkdir -p "$HF_CACHE"
docker rm -f "$NAME" >/dev/null 2>&1 || true

args=(
  --model "$MODEL"
  --served-model-name "$SERVED_NAME"
  --host 0.0.0.0 --port 8000
  --tensor-parallel-size "$TP"
  --max-model-len "$MAX_MODEL_LEN"
  --gpu-memory-utilization 0.90
  --enable-auto-tool-choice --tool-call-parser "$TOOL_PARSER"
  --structured-outputs-config.backend "$STRUCTURED_BACKEND"
)
if [[ -n "$REASONING_PARSER" ]]; then
  args+=(--reasoning-parser "$REASONING_PARSER")
fi
if [[ -n "${EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  args+=($EXTRA_ARGS)
fi

docker run -d --name "$NAME" --restart unless-stopped \
  --group-add=video --group-add=render \
  --cap-add=SYS_PTRACE --security-opt seccomp=unconfined \
  --device /dev/kfd --device /dev/dri \
  --ipc=host --shm-size 16g \
  -v "$HF_CACHE:/root/.cache/huggingface" \
  -e HF_TOKEN="${HF_TOKEN:-}" \
  -e VLLM_API_KEY="$VLLM_API_KEY" \
  -p "$PORT:8000" \
  "$IMAGE" "${args[@]}"

echo "Started $NAME ($MODEL). Waiting for /v1/models ..."
for _ in $(seq 1 180); do
  if curl -fsS -H "Authorization: Bearer $VLLM_API_KEY" "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
    echo "Ready: http://$(hostname -I | awk '{print $1}'):$PORT/v1  model=$SERVED_NAME"
    exit 0
  fi
  sleep 10
done
echo "vLLM did not become ready in 30 min; see: docker logs $NAME" >&2
exit 1

#!/usr/bin/env bash
# Bring up one pinned Ollama instance per GPU so the qwen35b extraction can
# share all 4 cards. Weights load once per GPU; OLLAMA_NUM_PARALLEL lets each
# instance serve several concurrent requests without loading weights again.
#
#   NGPU        number of GPUs / instances (default 4)
#   NUM_PARALLEL concurrent requests per instance (default 2 -> 2 workers/GPU)
#   CTX         context length cap (default 16384; inputs are ~5k chars)
#   BASE_PORT   first port; instance k listens on BASE_PORT+k (default 11430)
#
# Idempotent-ish: kills any prior `ollama serve` first, then starts fresh.
set -euo pipefail
cd "$(dirname "$0")/.."

NGPU="${NGPU:-4}"
NUM_PARALLEL="${NUM_PARALLEL:-2}"
CTX="${CTX:-16384}"
BASE_PORT="${BASE_PORT:-11430}"
MODEL="${QWEN_MODEL:-qwen3.6:35b-a3b}"
mkdir -p logs

echo "Stopping any existing ollama serve..."
pkill -f "ollama serve" 2>/dev/null || true
sleep 2

for k in $(seq 0 $((NGPU-1))); do
  port=$((BASE_PORT+k))
  echo "Starting instance $k -> GPU $k, port $port (ctx=$CTX, parallel=$NUM_PARALLEL)"
  CUDA_VISIBLE_DEVICES=$k \
  OLLAMA_HOST=127.0.0.1:$port \
  OLLAMA_CONTEXT_LENGTH=$CTX \
  OLLAMA_NUM_PARALLEL=$NUM_PARALLEL \
  OLLAMA_KEEP_ALIVE=-1 \
    nohup ollama serve > "logs/ollama_gpu${k}.log" 2>&1 &
  disown
done
sleep 5

echo "Warming model $MODEL on each instance (loads weights onto each GPU)..."
for k in $(seq 0 $((NGPU-1))); do
  port=$((BASE_PORT+k))
  OLLAMA_HOST=127.0.0.1:$port ollama run "$MODEL" "ok" >/dev/null 2>&1 &
done
wait
echo "--- ollama ps per instance (expect 100% GPU on each) ---"
for k in $(seq 0 $((NGPU-1))); do
  port=$((BASE_PORT+k))
  echo "### GPU $k (port $port):"
  OLLAMA_HOST=127.0.0.1:$port ollama ps
done

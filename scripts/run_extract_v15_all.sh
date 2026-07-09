#!/usr/bin/env bash
# Full FRESH sharded qwen35b extraction over ALL page inputs (from page 1),
# spread across the pinned per-GPU Ollama instances started by
# scripts/start_ollama_gpus.sh. Each worker owns a distinct shard file, so the
# run is crash-safe/resumable and there are no cross-worker write races.
#
#   NSHARD   total worker shards (default 16 = 4 GPUs x 4 workers/GPU)
#   NGPU     number of pinned instances (default 4), ports BASE_PORT+ (k%NGPU)
#   BASE_PORT first instance port (default 11430)
#   OUT      output dir (default data/wiki/_extract_v15_qwen35b)
#   FRESH    1 => wipe OUT first (default 1). Set 0 to resume an interrupted run.
set -euo pipefail
cd "$(dirname "$0")/.."

NSHARD="${NSHARD:-16}"
NGPU="${NGPU:-4}"
BASE_PORT="${BASE_PORT:-11430}"
OUT="${OUT:-data/wiki/_extract_v15_qwen35b}"
FRESH="${FRESH:-1}"
MODEL="${QWEN_MODEL:-qwen3.6:35b-a3b}"

if [[ "$FRESH" == "1" ]]; then
  echo "FRESH run: wiping $OUT"
  rm -rf "$OUT"
fi
mkdir -p "$OUT" logs

echo "Launching $NSHARD shards over $NGPU GPUs -> $OUT  (model=$MODEL)"
for k in $(seq 0 $((NSHARD-1))); do
  port=$((BASE_PORT + (k % NGPU)))
  QWEN_MODEL="$MODEL" nohup .venv/bin/python scripts/run_prompt_v15_test.py \
    --shard "$k/$NSHARD" --base-url "http://127.0.0.1:$port/v1" --out "$OUT" \
    > "logs/extract_v15_shard${k}of${NSHARD}.log" 2>&1 &
  disown
done
echo "All $NSHARD workers launched (survive disconnect via nohup)."
echo "Progress:  cat $OUT/processed.shard*.jsonl | wc -l   (of 25246)"
echo "When all finish: .venv/bin/python scripts/run_prompt_v15_test.py --merge --out $OUT"

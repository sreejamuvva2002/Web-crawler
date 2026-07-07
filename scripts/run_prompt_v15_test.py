#!/usr/bin/env python3
"""Run the v15 (hybrid) page prompt over page inputs.

Uses the same LLM client as the pipeline but the v15 hybrid schema
(entity identity + provenance + a flat exhaustive ``facts`` list). Two modes:

  * TEST     -- small samples for prompt/model comparison (--limit / --pages).
               Writes one ``<page>_v15.json`` per page for easy inspection.
  * BULK     -- sharded, resume-safe extraction over the whole corpus (--shard),
               for parallel multi-GPU runs. Streams to one jsonl per shard and
               records progress so a crashed worker restarts where it left off.

Model + endpoint are selected via env (QWEN_MODEL, LLM_BASE_URL) or --base-url,
so N workers can each point at a different per-GPU Ollama/vLLM instance.

Examples:
    # test / comparison
    QWEN_MODEL=gpt-oss:120b python scripts/run_prompt_v15_test.py --limit 2
    QWEN_MODEL=qwen3.6:35b-a3b python scripts/run_prompt_v15_test.py --pages page_000001,page_000002

    # bulk: 4 shards, one per GPU/instance (run each on its own port)
    QWEN_MODEL=qwen3.6:35b-a3b python scripts/run_prompt_v15_test.py \
        --shard 0/4 --base-url http://127.0.0.1:11434/v1 --out data/wiki/_extract_v15_qwen35b
    # ...shards 1/4 (:11435), 2/4 (:11436), 3/4 (:11437) in parallel...

    # merge shard outputs into one jsonl when all workers finish
    python scripts/run_prompt_v15_test.py --merge --out data/wiki/_extract_v15_qwen35b
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

# Make `src` importable no matter the cwd (so bulk workers launch without PYTHONPATH).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

VERSION = "v15"


def parse_shard(spec: str) -> tuple[int, int]:
    i, n = spec.split("/")
    i, n = int(i), int(n)
    if not (0 <= i < n) or n < 1:
        raise SystemExit(f"--shard must be i/N with 0 <= i < N; got {spec!r}")
    return i, n


def do_merge(out: Path) -> None:
    """Concatenate every shard's all_records jsonl into one deduped file."""
    shards = sorted(out.glob(f"all_records_{VERSION}.shard*.jsonl"))
    if not shards:
        raise SystemExit(f"No shard files (all_records_{VERSION}.shard*.jsonl) in {out}")
    seen, merged, total = set(), [], 0
    for sp in shards:
        for line in sp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            total += 1
            r = json.loads(line)
            # De-dup on (page_id, entity) in case a page was retried across restarts.
            key = (r.get("page_id"), r.get("canonical_name") or r.get("entity_name"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(line)
    dest = out / f"all_records_{VERSION}.jsonl"
    dest.write_text("\n".join(merged) + "\n", encoding="utf-8")
    print(f"Merged {len(shards)} shard(s): {total} lines -> {len(merged)} unique records -> {dest}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=2, help="TEST: run the first N page inputs")
    ap.add_argument("--pages", default=None, help="TEST: comma-separated page ids; overrides --limit")
    ap.add_argument("--shard", default=None, help="BULK: this worker's shard as i/N (0-based)")
    ap.add_argument("--base-url", default=None, help="override LLM_BASE_URL (per-GPU endpoint)")
    ap.add_argument("--merge", action="store_true", help="merge shard outputs in --out, then exit")
    ap.add_argument("--mock-llm", action="store_true", help="use canned outputs (no server)")
    ap.add_argument("--out", default=None, help="output dir (default: dated v15 dir)")
    args = ap.parse_args()

    # --base-url must win over .env; set it before load_settings reads the env.
    if args.base_url:
        os.environ["LLM_BASE_URL"] = args.base_url

    from src.common.config import PAGE_INPUTS_DIR, WIKI_DIR, ensure_data_dirs, load_settings
    from src.common.io_utils import append_jsonl, iter_jsonl
    from src.wiki_generation.llm_client import get_llm_client
    from src.wiki_generation.qwen_page_wiki_prompt_v15 import FactRecordsResponse, build_prompt

    settings = load_settings(None)
    ensure_data_dirs()

    out = Path(args.out) if args.out else (
        WIKI_DIR / f"_prompt_test_samples_{dt.date.today():%Y%m%d}_{VERSION}"
    )
    out.mkdir(parents=True, exist_ok=True)

    if args.merge:
        do_merge(out)
        return

    # ---- select this run's page inputs ----
    inputs = sorted(PAGE_INPUTS_DIR.glob("page_*.json"))
    bulk = args.shard is not None
    if args.pages:
        wanted = {p.strip() for p in args.pages.split(",")}
        inputs = [p for p in inputs if p.stem in wanted]
        shard_tag = ""
    elif bulk:
        i, n = parse_shard(args.shard)
        inputs = [p for idx, p in enumerate(inputs) if idx % n == i]
        shard_tag = f".shard{i}of{n}"
    else:
        inputs = inputs[: args.limit]
        shard_tag = ""

    records_path = out / f"all_records_{VERSION}{shard_tag}.jsonl"
    processed_path = out / f"processed{shard_tag}.jsonl"
    failures_path = out / f"failures_{VERSION}{shard_tag}.jsonl"

    # ---- resume: skip pages already processed by THIS shard ----
    done = {row["page_id"] for row in iter_jsonl(processed_path)}
    pending = [p for p in inputs if p.stem not in done]

    client = get_llm_client(settings, mock=args.mock_llm)
    model = getattr(client, "model_name", settings.qwen_model)
    today = dt.date.today().isoformat()
    print(f"v15 {'bulk '+args.shard if bulk else 'test'}: {len(inputs)} assigned, "
          f"{len(done)} already done, {len(pending)} to run | model={model} "
          f"| base_url={settings.llm_base_url} | out={out}")

    n_records = n_facts = n_fail = 0
    for path in pending:
        page_input = json.loads(path.read_text(encoding="utf-8"))
        page_id = page_input["page_id"]
        try:
            response: FactRecordsResponse = client.generate(
                FactRecordsResponse, build_prompt(page_input, settings)
            )
        except Exception as exc:  # noqa: BLE001 - per-page isolation, like the pipeline
            # Not marked processed, so a rerun retries it.
            append_jsonl(failures_path, [{"page_id": page_id, "error": str(exc)[:500]}])
            n_fail += 1
            print(f"  {page_id}: FAILED - {str(exc)[:120]}")
            continue

        records = []
        for rec in response.records:
            data = rec.model_dump()
            # Provenance + publication date are stamped from the page input, never
            # trusted from the model (publication_date drives freshness tracking).
            data["source_url"] = page_input.get("source_url", "")
            data["source_title"] = page_input.get("source_title", "")
            data["source_domain"] = page_input.get("source_domain", "")
            data["publication_date"] = (page_input.get("publication_date") or "").strip()
            data["date_precision"] = (page_input.get("date_precision") or "none").strip()
            data["page_id"] = page_id
            data["generated_by_model"] = model
            data["generation_date"] = today
            data["prompt_version"] = VERSION
            records.append(data)

        # Stream to disk immediately, then mark processed -> crash-safe + resumable.
        append_jsonl(records_path, records)
        if not bulk:  # TEST mode also writes a per-page file for easy inspection
            (out / f"{page_id}_{VERSION}.json").write_text(
                json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        append_jsonl(processed_path, [{"page_id": page_id, "record_count": len(records)}])
        n_records += len(records)
        n_facts += sum(len(r.get("facts") or []) for r in records)
        if records:
            r0 = records[0]
            print(f"  {page_id}: {r0.get('canonical_name') or r0.get('entity_name') or '?'}"
                  f" [pub {r0.get('publication_date') or '?'}] -> "
                  f"{sum(len(r.get('facts') or []) for r in records)} facts, "
                  f"{sum(len(r.get('links') or []) for r in records)} links")
        else:
            print(f"  {page_id}: [] (no relevant record)")

    (out / f"summary_{VERSION}{shard_tag}.json").write_text(
        json.dumps({
            "prompt_version": VERSION, "model": model, "base_url": settings.llm_base_url,
            "shard": args.shard, "assigned": len(inputs), "ran_now": len(pending),
            "records_this_run": n_records, "facts_this_run": n_facts,
            "failures_this_run": n_fail, "generated": today,
        }, indent=2),
        encoding="utf-8",
    )
    print(f"Done: {n_records} records, {n_facts} facts, {n_fail} failures "
          f"this run -> {records_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run the v14 (hybrid) page prompt over the first N page inputs and save a sample.

Uses the same LLM client as the pipeline but the v14 hybrid schema
(entity identity + provenance + a flat exhaustive ``facts`` list). Writes to a
versioned sample dir so v14 recall can be compared against the v13 samples
without touching the shared pipeline files.

Usage:
    QWEN_MODEL=gpt-oss:120b python scripts/run_prompt_v14_test.py --limit 2
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from src.common.config import PAGE_INPUTS_DIR, WIKI_DIR, ensure_data_dirs, load_settings
from src.wiki_generation.llm_client import get_llm_client
from src.wiki_generation.qwen_page_wiki_prompt_v14 import (
    PAGE_WIKI_PROMPT_VERSION,
    FactRecordsResponse,
    build_prompt,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=2, help="how many of the first page inputs to run")
    ap.add_argument("--mock-llm", action="store_true", help="use canned outputs (no server)")
    ap.add_argument("--out", default=None, help="output sample dir (default: dated v14 dir)")
    args = ap.parse_args()

    settings = load_settings(None)
    ensure_data_dirs()

    out = Path(args.out) if args.out else (
        WIKI_DIR / f"_prompt_test_samples_{dt.date.today():%Y%m%d}_{PAGE_WIKI_PROMPT_VERSION}"
    )
    out.mkdir(parents=True, exist_ok=True)

    inputs = sorted(PAGE_INPUTS_DIR.glob("page_*.json"))[: args.limit]
    client = get_llm_client(settings, mock=args.mock_llm)
    model = getattr(client, "model_name", settings.qwen_model)
    today = dt.date.today().isoformat()

    all_records: list[dict] = []
    failures: list[dict] = []
    print(f"v14 test: {len(inputs)} page(s), model={model}, out={out}")

    for path in inputs:
        page_input = json.loads(path.read_text(encoding="utf-8"))
        page_id = page_input["page_id"]
        try:
            response: FactRecordsResponse = client.generate(
                FactRecordsResponse, build_prompt(page_input, settings)
            )
        except Exception as exc:  # noqa: BLE001 - per-page isolation, like the pipeline
            failures.append({"page_id": page_id, "error": str(exc)[:500]})
            (out / f"{page_id}_{PAGE_WIKI_PROMPT_VERSION}.json").write_text(
                json.dumps({"error": str(exc)[:500]}), encoding="utf-8"
            )
            print(f"  {page_id}: FAILED - {str(exc)[:120]}")
            continue

        records = []
        for rec in response.records:
            data = rec.model_dump()
            # Provenance is stamped from the page input, never trusted from the model.
            data["source_url"] = page_input.get("source_url", "")
            data["source_title"] = page_input.get("source_title", "")
            data["source_domain"] = page_input.get("source_domain", "")
            data["page_id"] = page_id
            data["generated_by_model"] = model
            data["generation_date"] = today
            data["prompt_version"] = PAGE_WIKI_PROMPT_VERSION
            records.append(data)
            print(f"  {page_id}: {data.get('canonical_name') or data.get('entity_name') or '?'}"
                  f" -> {len(data.get('facts') or [])} facts")

        all_records.extend(records)
        (out / f"{page_id}_{PAGE_WIKI_PROMPT_VERSION}.json").write_text(
            json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    with (out / f"all_records_{PAGE_WIKI_PROMPT_VERSION}.jsonl").open("w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out / f"summary_{PAGE_WIKI_PROMPT_VERSION}.json").write_text(
        json.dumps(
            {
                "prompt_version": PAGE_WIKI_PROMPT_VERSION,
                "model": model,
                "pages": [p.stem for p in inputs],
                "records": len(all_records),
                "total_facts": sum(len(r.get("facts") or []) for r in all_records),
                "failures": failures,
                "generated": today,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Done: {len(all_records)} record(s), "
          f"{sum(len(r.get('facts') or []) for r in all_records)} facts, "
          f"{len(failures)} failure(s) -> {out}")


if __name__ == "__main__":
    main()

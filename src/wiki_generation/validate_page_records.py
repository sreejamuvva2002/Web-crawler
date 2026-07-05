"""Stage 5, validation: run every raw page record through schema/field checks,
the source-grounding check (against the page input's markdown), and duplicate-
fact removal -> wiki_records_validated.jsonl / wiki_records_failed.jsonl.

Full rewrite from the raw file on every run (idempotent). Generation failures
already in the failed file are preserved; earlier validation failures are
recomputed."""

import json

from src.common.cli import build_parser
from src.common.config import PAGE_INPUTS_DIR, WIKI_DIR, load_settings
from src.common.io_utils import read_jsonl, write_jsonl
from src.common.logging_setup import get_logger
from src.validation.check_source_grounding import is_grounded
from src.validation.remove_duplicate_facts import dedupe_records
from src.validation.validate_wiki_records import validate_page_record

log = get_logger("wiki_generation.validate_page_records", "validation.log")

RAW_PATH = WIKI_DIR / "wiki_records_raw.jsonl"
VALIDATED_PATH = WIKI_DIR / "wiki_records_validated.jsonl"
FAILED_PATH = WIKI_DIR / "wiki_records_failed.jsonl"


def _page_markdown(page_id: str, cache: dict[str, str]) -> str:
    if page_id not in cache:
        path = PAGE_INPUTS_DIR / f"{page_id}.json"
        if path.exists():
            cache[page_id] = json.loads(path.read_text(encoding="utf-8")).get("page_markdown", "")
        else:
            cache[page_id] = ""
    return cache[page_id]


def main() -> None:
    args = build_parser(__doc__).parse_args()
    settings = load_settings(args.config_dir)
    threshold = int(settings.wiki_schema.get("evidence_fuzzy_threshold", 85))

    records = read_jsonl(RAW_PATH)
    if args.limit:
        records = records[: args.limit]

    markdown_cache: dict[str, str] = {}
    passed, failed = [], []
    for record in records:
        reasons = validate_page_record(record, settings)
        if "missing_evidence" not in reasons:
            page = _page_markdown(record.get("page_id", ""), markdown_cache)
            if not is_grounded(record.get("evidence_text", ""), page, threshold):
                reasons.append("unsupported_claim")
        if reasons:
            record["validation_status"] = "failed"
            record["rejection_reasons"] = reasons
            failed.append(record)
        else:
            record["validation_status"] = "passed"
            passed.append(record)

    passed, duplicates = dedupe_records(passed)
    failed.extend(duplicates)

    if args.dry_run:
        log.info("[dry-run] %d records would pass, %d fail", len(passed), len(failed))
        return

    write_jsonl(VALIDATED_PATH, passed)
    generation_failures = [
        row for row in read_jsonl(FAILED_PATH) if row.get("failure_stage") == "generation"
    ]
    write_jsonl(FAILED_PATH, generation_failures + failed)
    log.info(
        "Validated %d raw records: %d passed -> %s, %d failed -> %s",
        len(records),
        len(passed),
        VALIDATED_PATH,
        len(failed),
        FAILED_PATH,
    )


if __name__ == "__main__":
    main()

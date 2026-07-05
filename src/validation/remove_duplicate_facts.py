"""Duplicate-fact removal (spec Stage 6): the same (source, entity, evidence)
combination must appear only once. Importable dedupe function; as a CLI it
rewrites wiki_records_validated.jsonl (idempotent)."""

import re

from src.common.cli import build_parser
from src.common.config import WIKI_DIR, load_settings
from src.common.io_utils import read_jsonl, write_jsonl
from src.common.logging_setup import get_logger

log = get_logger("validation.remove_duplicate_facts", "validation.log")

RECORDS_VALIDATED_PATH = WIKI_DIR / "wiki_records_validated.jsonl"


def _fact_key(record: dict) -> tuple[str, str, str]:
    return (
        (record.get("source_url") or "").strip(),
        (record.get("entity_name") or "").strip().casefold(),
        re.sub(r"\s+", " ", record.get("evidence_text") or "").strip().casefold(),
    )


def dedupe_records(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """First occurrence wins; returns (kept, dropped)."""
    seen: set[tuple[str, str, str]] = set()
    kept, dropped = [], []
    for record in records:
        key = _fact_key(record)
        if key in seen:
            record["validation_status"] = "failed"
            record.setdefault("rejection_reasons", []).append("duplicate_record")
            dropped.append(record)
        else:
            seen.add(key)
            kept.append(record)
    return kept, dropped


def main() -> None:
    args = build_parser(__doc__).parse_args()
    load_settings(args.config_dir)

    records = read_jsonl(RECORDS_VALIDATED_PATH)
    kept, dropped = dedupe_records(records)
    if args.dry_run:
        log.info("[dry-run] %d records kept, %d duplicates dropped", len(kept), len(dropped))
        return
    write_jsonl(RECORDS_VALIDATED_PATH, kept)
    log.info("Deduped %d validated records -> %d kept, %d duplicates removed", len(records), len(kept), len(dropped))


if __name__ == "__main__":
    main()

"""Stage 7: export validated entity profiles as the final LLM Wiki CSV
(data/exports/final_llm_wiki.csv). List/object fields are JSON-encoded in their
CSV cells. src.wiki_generation.export_llm_wiki writes the same table to
data/wiki/final_llm_wiki.csv (both artifacts are in the spec)."""

import json
from pathlib import Path

from src.common.cli import build_parser
from src.common.config import EXPORTS_DIR, WIKI_DIR, ensure_data_dirs, load_settings
from src.common.io_utils import read_jsonl, write_csv_dicts
from src.common.logging_setup import get_logger

log = get_logger("export.export_final_wiki", "validation.log")

ENTITIES_VALIDATED_PATH = WIKI_DIR / "wiki_entities_validated.jsonl"

FINAL_WIKI_COLUMNS = [
    "canonical_name",
    "aliases",
    "entity_type",
    "summary",
    "locations",
    "supply_chain_categories",
    "products_or_services",
    "customers_or_oems",
    "investment_amounts",
    "jobs",
    "facility_status",
    "related_entities",
    "source_count",
    "sources",
    "confidence_score",
    "conflicts_or_uncertainties",
    "notes",
]

_JSON_FIELDS = {
    "aliases",
    "locations",
    "supply_chain_categories",
    "products_or_services",
    "customers_or_oems",
    "investment_amounts",
    "jobs",
    "related_entities",
    "sources",
    "conflicts_or_uncertainties",
}


def build_final_wiki_rows(entities: list[dict]) -> list[dict]:
    rows = []
    for entity in entities:
        row = {}
        for column in FINAL_WIKI_COLUMNS:
            value = entity.get(column, "")
            if column == "source_count":
                value = entity.get("source_count") or len(entity.get("sources") or [])
            if column in _JSON_FIELDS:
                value = json.dumps(value or [], ensure_ascii=False)
            row[column] = value
        rows.append(row)
    return rows


def export_final_wiki(out_path: Path, limit: int | None = None, dry_run: bool = False) -> int:
    entities = read_jsonl(ENTITIES_VALIDATED_PATH)
    if limit:
        entities = entities[:limit]
    rows = build_final_wiki_rows(entities)
    if not dry_run:
        write_csv_dicts(out_path, rows, FINAL_WIKI_COLUMNS)
    return len(rows)


def main() -> None:
    args = build_parser(__doc__).parse_args()
    load_settings(args.config_dir)
    ensure_data_dirs()
    out = EXPORTS_DIR / "final_llm_wiki.csv"
    count = export_final_wiki(out, args.limit, args.dry_run)
    prefix = "[dry-run] would export" if args.dry_run else "Exported"
    log.info("%s %d entities -> %s", prefix, count, out)


if __name__ == "__main__":
    main()

"""Stage 7: export final_sources.csv (one row per entity-source pair, evidence
preserved) and final_url_inventory.csv (the full frontier)."""

from src.common.cli import build_parser
from src.common.config import EXPORTS_DIR, WIKI_DIR, ensure_data_dirs, load_settings
from src.common.io_utils import read_jsonl, write_csv_dicts
from src.common.logging_setup import get_logger
from src.frontier.frontier_manager import Frontier

log = get_logger("export.export_sources", "validation.log")

ENTITIES_VALIDATED_PATH = WIKI_DIR / "wiki_entities_validated.jsonl"

SOURCE_COLUMNS = ["canonical_name", "entity_type", "source_url", "source_title", "source_domain", "evidence_text"]


def main() -> None:
    args = build_parser(__doc__).parse_args()
    load_settings(args.config_dir)
    ensure_data_dirs()

    rows = []
    for entity in read_jsonl(ENTITIES_VALIDATED_PATH):
        for source in entity.get("sources", []):
            rows.append(
                {
                    "canonical_name": entity.get("canonical_name", ""),
                    "entity_type": entity.get("entity_type", ""),
                    "source_url": source.get("source_url", ""),
                    "source_title": source.get("source_title", ""),
                    "source_domain": source.get("source_domain", ""),
                    "evidence_text": source.get("evidence_text", ""),
                }
            )
    if args.limit:
        rows = rows[: args.limit]

    sources_path = EXPORTS_DIR / "final_sources.csv"
    inventory_path = EXPORTS_DIR / "final_url_inventory.csv"
    if args.dry_run:
        log.info("[dry-run] would export %d source rows -> %s and the frontier -> %s", len(rows), sources_path, inventory_path)
        return
    write_csv_dicts(sources_path, rows, SOURCE_COLUMNS)
    with Frontier() as frontier:
        frontier.export_csv(inventory_path)
    log.info("Exported %d source rows -> %s; URL inventory -> %s", len(rows), sources_path, inventory_path)


if __name__ == "__main__":
    main()

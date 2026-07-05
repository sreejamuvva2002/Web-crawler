"""Stage 2: load prioritized candidates into the frontier. high/medium ->
queued, low -> needs_review, skip -> rejected (labeled, never deleted).
Upserts on normalized_url, so reruns are safe."""

from src.common.cli import build_parser
from src.common.config import URLS_DIR, load_settings
from src.common.io_utils import read_csv_dicts
from src.common.logging_setup import get_logger
from src.frontier.frontier_manager import CSV_PATH, Frontier

log = get_logger("frontier.update_frontier", "discovery.log")

PRIORITIZED_PATH = URLS_DIR / "url_candidates_prioritized.csv"

_STATUS_BY_PRIORITY = {"high": "queued", "medium": "queued", "low": "needs_review", "skip": "rejected"}


def main() -> None:
    args = build_parser(__doc__).parse_args()
    load_settings(args.config_dir)

    candidates = read_csv_dicts(PRIORITIZED_PATH)
    if args.limit:
        candidates = candidates[: args.limit]
    rows = [
        {
            "url": c["url"],
            "normalized_url": c["normalized_url"],
            "domain": c.get("domain", ""),
            "priority": c.get("priority", "medium"),
            "status": _STATUS_BY_PRIORITY.get(c.get("priority", "medium"), "needs_review"),
            "discovered_from": c.get("source_type", ""),
            "query_used": c.get("query_used", ""),
            "first_seen_date": c.get("discovered_date", ""),
            "notes": c.get("notes", ""),
        }
        for c in candidates
        if c.get("normalized_url")
    ]

    if args.dry_run:
        log.info("[dry-run] would upsert %d candidates into the frontier", len(rows))
        return
    with Frontier() as frontier:
        inserted = frontier.upsert_urls(rows)
        frontier.export_csv()
        log.info(
            "Upserted %d candidates (%d new). Status counts: %s. Exported %s",
            len(rows),
            inserted,
            frontier.counts(),
            CSV_PATH,
        )


if __name__ == "__main__":
    main()

"""Stage 2: attach a priority (high/medium/low/skip) to every deduped candidate
-> url_candidates_prioritized.csv. Pure transform; safe to rerun."""

from src.common.cli import build_parser
from src.common.columns import URL_CANDIDATE_COLUMNS
from src.common.config import URLS_DIR, load_settings
from src.common.io_utils import read_csv_dicts, write_csv_dicts
from src.common.logging_setup import get_logger
from src.url_processing.classify_domains import classify_priority

log = get_logger("url_processing.prioritize_urls", "discovery.log")

DEDUPED_PATH = URLS_DIR / "url_candidates_deduped.csv"
PRIORITIZED_PATH = URLS_DIR / "url_candidates_prioritized.csv"

PRIORITIZED_COLUMNS = URL_CANDIDATE_COLUMNS + ["priority"]


def main() -> None:
    args = build_parser(__doc__).parse_args()
    settings = load_settings(args.config_dir)

    rows = read_csv_dicts(DEDUPED_PATH)
    for row in rows:
        row["priority"] = classify_priority(row.get("url", ""), settings.domain_priority)

    order = {"high": 0, "medium": 1, "low": 2, "skip": 3}
    rows.sort(key=lambda r: order.get(r["priority"], 1))

    if args.dry_run:
        log.info("[dry-run] would prioritize %d rows", len(rows))
        return
    write_csv_dicts(PRIORITIZED_PATH, rows, PRIORITIZED_COLUMNS)
    log.info("Prioritized %d candidates -> %s", len(rows), PRIORITIZED_PATH)


if __name__ == "__main__":
    main()

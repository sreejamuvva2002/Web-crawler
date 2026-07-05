"""Stage 2: dedupe raw candidates on normalized_url (first seen wins) into
url_candidates_deduped.csv. Losing rows stay in the raw file labeled
status=duplicate — labeled, never deleted (spec Rule 5)."""

from src.common.cli import build_parser
from src.common.columns import URL_CANDIDATE_COLUMNS
from src.common.config import URLS_DIR, load_settings
from src.common.io_utils import read_csv_dicts, write_csv_dicts
from src.common.logging_setup import get_logger

log = get_logger("url_processing.deduplicate_urls", "discovery.log")

RAW_PATH = URLS_DIR / "url_candidates_raw.csv"
DEDUPED_PATH = URLS_DIR / "url_candidates_deduped.csv"


def main() -> None:
    args = build_parser(__doc__).parse_args()
    load_settings(args.config_dir)

    rows = read_csv_dicts(RAW_PATH)
    winners: dict[str, dict] = {}
    duplicates = 0
    for row in rows:
        key = row.get("normalized_url", "")
        if not key:
            continue
        if key in winners:
            row["status"] = "duplicate"
            duplicates += 1
        else:
            if row.get("status") == "duplicate":
                row["status"] = "new"
            winners[key] = row

    if args.dry_run:
        log.info("[dry-run] %d unique / %d duplicates of %d rows", len(winners), duplicates, len(rows))
        return
    write_csv_dicts(RAW_PATH, rows, URL_CANDIDATE_COLUMNS)
    write_csv_dicts(DEDUPED_PATH, list(winners.values()), URL_CANDIDATE_COLUMNS)
    log.info(
        "Deduped %d raw rows -> %d unique (%d labeled duplicate) in %s",
        len(rows),
        len(winners),
        duplicates,
        DEDUPED_PATH,
    )


if __name__ == "__main__":
    main()

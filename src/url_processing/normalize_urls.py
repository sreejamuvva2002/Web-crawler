"""Stage 2: recompute normalized_url and domain for every raw candidate row.
Pure transform; atomically rewrites url_candidates_raw.csv (safe to rerun)."""

from src.common.cli import build_parser
from src.common.columns import URL_CANDIDATE_COLUMNS
from src.common.config import URLS_DIR, load_settings
from src.common.io_utils import read_csv_dicts, write_csv_dicts
from src.common.logging_setup import get_logger
from src.common.url_utils import get_domain, normalize_url

log = get_logger("url_processing.normalize_urls", "discovery.log")

RAW_PATH = URLS_DIR / "url_candidates_raw.csv"


def main() -> None:
    args = build_parser(__doc__).parse_args()
    load_settings(args.config_dir)

    rows = read_csv_dicts(RAW_PATH)
    changed = 0
    for row in rows:
        normalized = normalize_url(row.get("url", ""))
        domain = get_domain(row.get("url", ""))
        if normalized != row.get("normalized_url") or domain != row.get("domain"):
            row["normalized_url"] = normalized
            row["domain"] = domain
            changed += 1

    if args.dry_run:
        log.info("[dry-run] %d/%d rows would change", changed, len(rows))
        return
    write_csv_dicts(RAW_PATH, rows, URL_CANDIDATE_COLUMNS)
    log.info("Normalized %d rows (%d changed) in %s", len(rows), changed, RAW_PATH)


if __name__ == "__main__":
    main()

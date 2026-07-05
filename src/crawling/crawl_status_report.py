"""Stage 4: report crawl outcomes — status counts, language mix, top failing domains."""

from collections import Counter

from src.common.cli import build_parser
from src.common.config import CRAWLED_DIR, load_settings
from src.common.io_utils import read_csv_dicts
from src.common.logging_setup import get_logger
from src.frontier.frontier_manager import Frontier

log = get_logger("crawling.crawl_status_report", "crawling.log")

METADATA_PATH = CRAWLED_DIR / "crawl_metadata.csv"


def main() -> None:
    args = build_parser(__doc__).parse_args()
    load_settings(args.config_dir)

    rows = read_csv_dicts(METADATA_PATH)
    if not rows:
        log.info("No crawl metadata at %s yet.", METADATA_PATH)
        return

    status = Counter(r.get("crawl_status", "") for r in rows)
    languages = Counter(r.get("language", "") for r in rows if r.get("crawl_status") == "success")
    duplicates = sum(1 for r in rows if r.get("is_duplicate_content") == "true")
    failing = Counter(r.get("domain", "") for r in rows if r.get("crawl_status") == "failed")

    log.info("Crawl status: %s", dict(status))
    log.info("Languages (successes): %s", dict(languages.most_common(10)))
    log.info("Duplicate-content pages: %d", duplicates)
    if failing:
        log.info("Top failing domains: %s", dict(failing.most_common(10)))
    with Frontier() as frontier:
        log.info("Frontier: %s", frontier.counts())


if __name__ == "__main__":
    main()

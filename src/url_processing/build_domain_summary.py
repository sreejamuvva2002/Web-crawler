"""Stage 2: per-domain rollup of deduped candidates -> domain_summary.csv."""

from collections import defaultdict

from src.common.cli import build_parser
from src.common.columns import DOMAIN_SUMMARY_COLUMNS
from src.common.config import URLS_DIR, load_settings
from src.common.io_utils import read_csv_dicts, write_csv_dicts
from src.common.logging_setup import get_logger
from src.url_processing.classify_domains import classify_priority

log = get_logger("url_processing.build_domain_summary", "discovery.log")

DEDUPED_PATH = URLS_DIR / "url_candidates_deduped.csv"
SUMMARY_PATH = URLS_DIR / "domain_summary.csv"


def main() -> None:
    args = build_parser(__doc__).parse_args()
    settings = load_settings(args.config_dir)

    by_domain: dict[str, list[dict]] = defaultdict(list)
    for row in read_csv_dicts(DEDUPED_PATH):
        if row.get("domain"):
            by_domain[row["domain"]].append(row)

    summary = []
    for domain, rows in sorted(by_domain.items(), key=lambda kv: -len(kv[1])):
        titles = [r["title"] for r in rows if r.get("title")][:3]
        summary.append(
            {
                "domain": domain,
                "url_count": len(rows),
                "priority": classify_priority(rows[0].get("url", domain), settings.domain_priority),
                "sample_titles": " | ".join(titles),
            }
        )

    if args.dry_run:
        log.info("[dry-run] would summarize %d domains", len(summary))
        return
    write_csv_dicts(SUMMARY_PATH, summary, DOMAIN_SUMMARY_COLUMNS)
    log.info("Summarized %d domains -> %s", len(summary), SUMMARY_PATH)


if __name__ == "__main__":
    main()

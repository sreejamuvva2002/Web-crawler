"""Stage 2: domain -> priority classification from configs/domain_priority.yaml.
Importable pure function; as a script it prints the classification breakdown of
the deduped candidates."""

from collections import Counter

from src.common.cli import build_parser
from src.common.config import URLS_DIR, load_settings
from src.common.io_utils import read_csv_dicts
from src.common.logging_setup import get_logger
from src.common.url_utils import get_host

log = get_logger("url_processing.classify_domains", "discovery.log")

DEDUPED_PATH = URLS_DIR / "url_candidates_deduped.csv"

# first match wins, in this order
_BUCKETS = [
    ("skip_domains", "skip"),
    ("high_priority", "high"),
    ("medium_priority", "medium"),
    ("low_priority", "low"),
]


def classify_priority(url_or_host: str, domain_priority: dict) -> str:
    """Return skip | high | medium | low for a URL or hostname. Patterns are
    substring matches against the full host; unmatched hosts default to medium."""
    host = get_host(url_or_host) if "/" in url_or_host or "." in url_or_host else url_or_host
    for config_key, priority in _BUCKETS:
        for pattern in domain_priority.get(config_key, []) or []:
            if pattern in host:
                return priority
    return "medium"


def main() -> None:
    args = build_parser(__doc__).parse_args()
    settings = load_settings(args.config_dir)

    counts: Counter[str] = Counter()
    for row in read_csv_dicts(DEDUPED_PATH):
        counts[classify_priority(row.get("url", ""), settings.domain_priority)] += 1
    if not counts:
        log.info("No deduped candidates at %s yet.", DEDUPED_PATH)
        return
    for priority, count in counts.most_common():
        log.info("%-7s %d", priority, count)


if __name__ == "__main__":
    main()

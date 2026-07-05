"""Stage 2/4: requeue failed frontier URLs that still have retry budget."""

from src.common.cli import build_parser
from src.common.config import load_settings
from src.common.logging_setup import get_logger
from src.frontier.frontier_manager import Frontier

log = get_logger("frontier.retry_failed_urls", "crawling.log")


def main() -> None:
    parser = build_parser(__doc__)
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args()
    load_settings(args.config_dir)

    with Frontier() as frontier:
        if args.dry_run:
            failed = frontier.get_by_status(["failed"])
            eligible = [r for r in failed if r["retry_count"] < args.max_retries]
            log.info("[dry-run] %d of %d failed URLs would be requeued", len(eligible), len(failed))
            return
        requeued = frontier.requeue_failed(args.max_retries)
        frontier.export_csv()
        log.info("Requeued %d failed URLs (max_retries=%d)", requeued, args.max_retries)


if __name__ == "__main__":
    main()

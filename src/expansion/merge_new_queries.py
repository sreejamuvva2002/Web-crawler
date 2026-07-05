"""Stage 3: merge follow-up queries into the iteration's runnable query file
(data/urls/queries_iter_{n}.csv), deduping against every earlier iteration and
enforcing MAX_DISCOVERY_ITERATIONS and max_queries_per_iteration."""

from src.common.cli import build_parser
from src.common.columns import QUERY_COLUMNS
from src.common.config import URLS_DIR, load_settings
from src.common.io_utils import read_csv_dicts, write_csv_dicts
from src.common.logging_setup import get_logger
from src.discovery.generate_queries import queries_path

log = get_logger("expansion.merge_new_queries", "discovery.log")


def main() -> None:
    parser = build_parser(__doc__)
    parser.add_argument("--iteration", type=int, default=1, help="expansion iteration (>= 1)")
    args = parser.parse_args()
    settings = load_settings(args.config_dir)

    if args.iteration > settings.max_discovery_iterations:
        log.error(
            "Iteration %d exceeds MAX_DISCOVERY_ITERATIONS=%d — not merging (spec: no endless discovery).",
            args.iteration,
            settings.max_discovery_iterations,
        )
        raise SystemExit(1)

    prior: set[str] = set()
    for i in range(args.iteration):
        prior |= {r["query"].casefold() for r in read_csv_dicts(queries_path(i))}

    expanded = read_csv_dicts(URLS_DIR / f"expanded_queries_iter_{args.iteration}.csv")
    target_path = queries_path(args.iteration)
    existing = {r["query"].casefold(): r for r in read_csv_dicts(target_path)}

    max_new = args.limit or int(settings.search.get("max_queries_per_iteration", 100))
    added = 0
    for row in expanded:
        key = row["query"].casefold()
        if key in prior or key in existing:
            continue
        if added >= max_new:
            break
        existing[key] = row
        added += 1

    if args.dry_run:
        log.info("[dry-run] would merge %d new queries into %s", added, target_path)
        return
    write_csv_dicts(target_path, list(existing.values()), QUERY_COLUMNS)
    log.info(
        "Merged %d new queries (of %d candidates) into %s — run collect_urls --iteration %d next",
        added,
        len(expanded),
        target_path,
        args.iteration,
    )


if __name__ == "__main__":
    main()

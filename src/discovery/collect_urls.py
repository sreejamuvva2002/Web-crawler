"""Stage 1: run every status=new query through the enabled search providers and
append discovered URLs to data/urls/url_candidates_raw.csv.

Idempotent: already-searched queries are skipped; appended rows are deduped on
(normalized_url, query_used, search_engine). Per-query provider errors are logged
and the run continues; a provider failing its health check aborts the stage."""

import datetime as dt
import sys
import time

from src.common.cli import build_parser
from src.common.columns import QUERY_COLUMNS, URL_CANDIDATE_COLUMNS
from src.common.config import URLS_DIR, ensure_data_dirs, load_settings
from src.common.io_utils import append_csv_dicts, read_csv_dicts, write_csv_dicts
from src.common.logging_setup import get_logger
from src.common.url_utils import get_domain, normalize_url
from src.discovery.generate_queries import queries_path
from src.discovery.provider_base import ProviderError, get_enabled_providers

log = get_logger("discovery.collect_urls", "discovery.log")

RAW_PATH = URLS_DIR / "url_candidates_raw.csv"


def main() -> None:
    parser = build_parser(__doc__)
    parser.add_argument("--iteration", type=int, default=0, help="query iteration to run")
    parser.add_argument("--provider", default=None, help="restrict to a single provider by name")
    args = parser.parse_args()
    settings = load_settings(args.config_dir)
    ensure_data_dirs()

    qpath = queries_path(args.iteration)
    queries = read_csv_dicts(qpath)
    if not queries:
        log.error(
            "No queries at %s. Run generate_queries (iteration 0) or the expansion "
            "stage (iteration >= 1) first.",
            qpath,
        )
        sys.exit(1)

    try:
        providers = get_enabled_providers(settings)
        if args.provider:
            providers = [p for p in providers if p.name == args.provider]
            if not providers:
                raise ProviderError(f"Provider '{args.provider}' is not enabled.")
        for provider in providers:
            provider.health_check()
    except ProviderError as exc:
        log.error("%s", exc)
        sys.exit(1)

    pending = [q for q in queries if q.get("status") == "new"]
    if args.limit:
        pending = pending[: args.limit]
    log.info(
        "Iteration %d: %d pending queries via providers: %s",
        args.iteration,
        len(pending),
        ", ".join(p.name for p in providers),
    )
    if args.dry_run:
        log.info("[dry-run] stopping before any searches")
        return

    seen = {
        (row["normalized_url"], row["query_used"], row["search_engine"])
        for row in read_csv_dicts(RAW_PATH)
    }
    delay = float(settings.search.get("delay_between_queries_sec", 1.0))
    today = dt.date.today().isoformat()
    total_new = 0

    for query_row in pending:
        query = query_row["query"]
        new_rows = []
        for provider in providers:
            try:
                results = provider.search(query, settings.max_results_per_query)
            except Exception as exc:  # noqa: BLE001 - per-query isolation
                log.warning("provider=%s query=%r failed: %s", provider.name, query, exc)
                continue
            for result in results:
                normalized = normalize_url(result.url)
                key = (normalized, query, provider.name)
                if not normalized or key in seen:
                    continue
                seen.add(key)
                new_rows.append(
                    {
                        "url": result.url,
                        "normalized_url": normalized,
                        "domain": get_domain(result.url),
                        "title": result.title,
                        "snippet": result.snippet,
                        "query_used": query,
                        "search_engine": provider.name,
                        "rank": result.rank,
                        "discovered_date": today,
                        "source_type": query_row.get("source_type", ""),
                        "status": "new",
                        "notes": "",
                    }
                )
        append_csv_dicts(RAW_PATH, new_rows, URL_CANDIDATE_COLUMNS)
        total_new += len(new_rows)

        query_row["status"] = "searched"
        write_csv_dicts(qpath, queries, QUERY_COLUMNS)
        log.info("query=%r -> %d new candidates", query, len(new_rows))
        if delay and query_row is not pending[-1]:
            time.sleep(delay)

    log.info("Done: %d new URL candidates appended to %s", total_new, RAW_PATH)


if __name__ == "__main__":
    main()

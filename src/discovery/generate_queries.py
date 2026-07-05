"""Stage 1: expand query templates against the seed CSVs into the iteration-0
query list (data/urls/queries_iter_0.csv). Idempotent: reruns keep the status of
queries that already exist and only add new ones."""

from src.common.cli import build_parser
from src.common.columns import QUERY_COLUMNS
from src.common.config import INPUT_DIR, URLS_DIR, ensure_data_dirs, load_settings
from src.common.io_utils import read_csv_dicts, write_csv_dicts
from src.common.logging_setup import get_logger

log = get_logger("discovery.generate_queries", "discovery.log")


def queries_path(iteration: int):
    return URLS_DIR / f"queries_iter_{iteration}.csv"


def build_seed_queries(settings) -> list[dict]:
    templates = settings.query_templates
    queries: list[dict] = []

    for q in templates.get("general_queries", []):
        queries.append({"query": q, "source_type": "general"})
    for row in read_csv_dicts(INPUT_DIR / "seed_queries.csv"):
        if row.get("query"):
            queries.append({"query": row["query"], "source_type": row.get("source_type") or "general"})

    site_terms = templates.get("site_query_terms", [])
    for row in read_csv_dicts(INPUT_DIR / "seed_domains.csv"):
        if (row.get("use_site_queries") or "").strip().lower() == "true":
            for term in site_terms:
                queries.append({"query": f"site:{row['domain']} {term}", "source_type": "site"})

    for row in read_csv_dicts(INPUT_DIR / "seed_locations.csv"):
        location = (row.get("location") or "").strip()
        if not location:
            continue
        for template in templates.get("location_query_templates", []):
            queries.append({"query": template.format(location=location), "source_type": "location"})

    for row in read_csv_dicts(INPUT_DIR / "seed_companies.csv"):
        company = (row.get("company") or "").strip()
        if not company:
            continue
        for template in templates.get("company_query_templates", []):
            queries.append({"query": template.format(company=company), "source_type": "company"})

    return queries


def main() -> None:
    parser = build_parser(__doc__)
    args = parser.parse_args()
    settings = load_settings(args.config_dir)
    ensure_data_dirs()

    path = queries_path(0)
    existing = {row["query"].casefold(): row for row in read_csv_dicts(path)}

    added = 0
    for candidate in build_seed_queries(settings):
        key = candidate["query"].casefold()
        if key in existing:
            continue
        existing[key] = {
            "query": candidate["query"],
            "source_type": candidate["source_type"],
            "iteration": "0",
            "status": "new",
        }
        added += 1

    rows = list(existing.values())
    if args.limit:
        rows = rows[: args.limit]
    if args.dry_run:
        log.info("[dry-run] would write %d queries (%d new) to %s", len(rows), added, path)
        return
    write_csv_dicts(path, rows, QUERY_COLUMNS)
    log.info("Wrote %d queries (%d new) to %s", len(rows), added, path)


if __name__ == "__main__":
    main()

"""Stage 3: apply follow-up query templates to newly extracted entities ->
data/urls/expanded_queries_iter_{n}.csv."""

from src.common.cli import build_parser
from src.common.columns import QUERY_COLUMNS
from src.common.config import URLS_DIR, load_settings
from src.common.io_utils import read_csv_dicts, write_csv_dicts
from src.common.logging_setup import get_logger

log = get_logger("expansion.generate_followup_queries", "discovery.log")


def main() -> None:
    parser = build_parser(__doc__)
    parser.add_argument("--iteration", type=int, default=1, help="expansion iteration (>= 1)")
    args = parser.parse_args()
    settings = load_settings(args.config_dir)
    templates = settings.query_templates

    entities_path = URLS_DIR / f"expansion_entities_iter_{args.iteration}.csv"
    entities = read_csv_dicts(entities_path)
    if not entities:
        log.error("No entities at %s — run extract_entities_for_expansion first.", entities_path)
        raise SystemExit(1)

    seen: set[str] = set()
    rows = []
    for row in entities:
        entity = row["entity"]
        if row["entity_type"] == "company":
            queries = [t.format(company=entity) for t in templates.get("followup_company_templates", [])]
            source_type = "expansion_company"
        else:
            queries = [t.format(location=entity) for t in templates.get("followup_location_templates", [])]
            source_type = "expansion_location"
        for query in queries:
            if query.casefold() in seen:
                continue
            seen.add(query.casefold())
            rows.append(
                {"query": query, "source_type": source_type, "iteration": args.iteration, "status": "new"}
            )

    if args.limit:
        rows = rows[: args.limit]
    out_path = URLS_DIR / f"expanded_queries_iter_{args.iteration}.csv"
    if args.dry_run:
        log.info("[dry-run] would write %d follow-up queries to %s", len(rows), out_path)
        return
    write_csv_dicts(out_path, rows, QUERY_COLUMNS)
    log.info("Generated %d follow-up queries from %d entities -> %s", len(rows), len(entities), out_path)


if __name__ == "__main__":
    main()

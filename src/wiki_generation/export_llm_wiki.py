"""Stage 6/7: write the final LLM Wiki table to data/wiki/final_llm_wiki.csv
(same table src.export.export_final_wiki writes under data/exports/)."""

from src.common.cli import build_parser
from src.common.config import WIKI_DIR, ensure_data_dirs, load_settings
from src.common.logging_setup import get_logger
from src.export.export_final_wiki import export_final_wiki

log = get_logger("wiki_generation.export_llm_wiki", "wiki_generation.log")


def main() -> None:
    args = build_parser(__doc__).parse_args()
    load_settings(args.config_dir)
    ensure_data_dirs()
    out = WIKI_DIR / "final_llm_wiki.csv"
    count = export_final_wiki(out, args.limit, args.dry_run)
    prefix = "[dry-run] would export" if args.dry_run else "Exported"
    log.info("%s %d entities -> %s", prefix, count, out)


if __name__ == "__main__":
    main()

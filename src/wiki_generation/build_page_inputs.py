"""Stage 5: join crawl metadata with saved Markdown into one Qwen input JSON per
page (data/wiki/page_inputs/page_NNNNNN.json). Only successful, English,
non-duplicate pages qualify. Deterministic overwrite — safe to rerun.

--from-fixtures builds inputs from tests/fixtures/pages/ instead (offline runs
without a crawl)."""

import json

from src.common.cli import build_parser
from src.common.config import (
    CRAWLED_DIR,
    FIXTURES_DIR,
    PAGE_INPUTS_DIR,
    REPO_ROOT,
    ensure_data_dirs,
    load_settings,
)
from src.common.io_utils import read_csv_dicts
from src.common.logging_setup import get_logger

log = get_logger("wiki_generation.build_page_inputs", "wiki_generation.log")

METADATA_PATH = CRAWLED_DIR / "crawl_metadata.csv"


def _write_page_input(page_id: str, source_url: str, source_title: str, source_domain: str,
                      markdown_path: str, markdown: str, max_chars: int) -> None:
    payload = {
        "page_id": page_id,
        "source_url": source_url,
        "source_title": source_title,
        "source_domain": source_domain,
        "markdown_path": markdown_path,
        "page_markdown": markdown[:max_chars],
    }
    out = PAGE_INPUTS_DIR / f"{page_id}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_from_crawl(settings, limit: int | None, dry_run: bool) -> int:
    # keep the last metadata row per markdown_path (interrupted runs can append twice)
    latest: dict[str, dict] = {}
    for row in read_csv_dicts(METADATA_PATH):
        if row.get("markdown_path"):
            latest[row["markdown_path"]] = row

    eligible = [
        row
        for row in latest.values()
        if row.get("crawl_status") == "success"
        and row.get("language") == "en"
        and row.get("is_duplicate_content") != "true"
    ]
    if limit:
        eligible = eligible[:limit]

    max_chars = int(settings.llm.get("max_input_chars", 30000))
    built = 0
    for row in eligible:
        md_file = REPO_ROOT / row["markdown_path"]
        if not md_file.exists():
            log.warning("markdown file missing, skipping: %s", md_file)
            continue
        page_id = md_file.stem
        if dry_run:
            built += 1
            continue
        _write_page_input(
            page_id,
            row.get("url", ""),
            row.get("title", ""),
            row.get("domain", ""),
            row["markdown_path"],
            md_file.read_text(encoding="utf-8"),
            max_chars,
        )
        built += 1
    return built


def build_from_fixtures(settings, limit: int | None, dry_run: bool) -> int:
    manifest = FIXTURES_DIR / "pages" / "pages.json"
    if not manifest.exists():
        log.error("Fixture manifest missing: %s", manifest)
        raise SystemExit(1)
    entries = json.loads(manifest.read_text())
    if limit:
        entries = entries[:limit]
    max_chars = int(settings.llm.get("max_input_chars", 30000))
    for entry in entries:
        if dry_run:
            continue
        md_file = FIXTURES_DIR / "pages" / entry["markdown_file"]
        _write_page_input(
            entry["page_id"],
            entry.get("source_url", ""),
            entry.get("source_title", ""),
            entry.get("source_domain", ""),
            str(md_file.relative_to(REPO_ROOT)),
            md_file.read_text(encoding="utf-8"),
            max_chars,
        )
    return len(entries)


def main() -> None:
    parser = build_parser(__doc__)
    parser.add_argument("--from-fixtures", action="store_true")
    args = parser.parse_args()
    settings = load_settings(args.config_dir)
    ensure_data_dirs()

    if args.from_fixtures:
        built = build_from_fixtures(settings, args.limit, args.dry_run)
    else:
        built = build_from_crawl(settings, args.limit, args.dry_run)
    prefix = "[dry-run] would build" if args.dry_run else "Built"
    log.info("%s %d page inputs in %s", prefix, built, PAGE_INPUTS_DIR)


if __name__ == "__main__":
    main()

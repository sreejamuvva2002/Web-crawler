"""Stage 5: join crawl metadata with saved Markdown into one Qwen input JSON per
page (data/wiki/page_inputs/page_NNNNNN.json). Only successful, English,
non-duplicate pages qualify. Deterministic overwrite — safe to rerun.

--from-fixtures builds inputs from tests/fixtures/pages/ instead (offline runs
without a crawl)."""

import json

import trafilatura

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
from src.crawling.publication_date import date_from_text, extract_publication_date

log = get_logger("wiki_generation.build_page_inputs", "wiki_generation.log")

METADATA_PATH = CRAWLED_DIR / "crawl_metadata.csv"
# Backfilled publication dates for pages crawled before the crawler captured them
# (see scripts/backfill_publication_dates.py). Keyed by url.
PUBLICATION_DATES_PATH = CRAWLED_DIR / "publication_dates.csv"


def _load_publication_dates() -> dict[str, dict]:
    return {row["url"]: row for row in read_csv_dicts(PUBLICATION_DATES_PATH)}

# Below this, trafilatura likely stripped real content along with the boilerplate
# (e.g. paywalled/JS-rendered pages) — safer to fall back to raw markdown than
# hand the LLM a near-empty input.
MIN_EXTRACTED_CHARS = 200


def _extract_main_text(html_path_rel: str, markdown: str, max_chars: int) -> str:
    """Prefer trafilatura's boilerplate-stripped extraction of the saved raw HTML
    over head-truncating the raw markdown, which cuts off the article entirely on
    pages with long nav/boilerplate preludes (common on press-release and news
    sites) once it exceeds max_chars."""
    if html_path_rel:
        html_file = REPO_ROOT / html_path_rel
        if html_file.exists():
            html = html_file.read_text(encoding="utf-8", errors="ignore")
            extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
            if extracted and len(extracted) >= MIN_EXTRACTED_CHARS:
                return extracted[:max_chars]
    return markdown[:max_chars]


def _write_page_input(page_id: str, source_url: str, source_title: str, source_domain: str,
                      markdown_path: str, page_markdown: str,
                      publication_date: str = "", date_precision: str = "none") -> None:
    payload = {
        "page_id": page_id,
        "source_url": source_url,
        "source_title": source_title,
        "source_domain": source_domain,
        "publication_date": publication_date,
        "date_precision": date_precision,
        "markdown_path": markdown_path,
        "page_markdown": page_markdown,
    }
    out = PAGE_INPUTS_DIR / f"{page_id}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_from_crawl(settings, limit: int | None, dry_run: bool) -> int:
    # keep the last metadata row per markdown_path (interrupted runs can append twice)
    latest: dict[str, dict] = {}
    for row in read_csv_dicts(METADATA_PATH):
        if row.get("markdown_path"):
            latest[row["markdown_path"]] = row
    sidecar_dates = _load_publication_dates()

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
        markdown = md_file.read_text(encoding="utf-8")
        page_markdown = _extract_main_text(row.get("html_path", ""), markdown, max_chars)
        # Prefer the date the crawler captured; fall back to the backfill sidecar;
        # finally parse a visible dateline out of the page text itself.
        pub_date = (row.get("publication_date") or "").strip()
        precision = (row.get("date_precision") or "").strip()
        if not pub_date:
            hit = sidecar_dates.get(row.get("url", ""))
            if hit:
                pub_date = (hit.get("publication_date") or "").strip()
                precision = (hit.get("date_precision") or "").strip()
        if not pub_date:
            pub_date = date_from_text(page_markdown)
            if pub_date:
                precision = "body_dateline"
        # Last resort: re-derive from the saved raw HTML the same way the crawler
        # would (visible "Published/Posted" body labels, <time> tags, URL month).
        # These live outside the trafilatura-stripped markdown, so the dateline
        # pass above misses them (e.g. `Published">June 05, 2025`, `/2022/11/`).
        if not pub_date:
            html_rel = row.get("html_path", "")
            html_file = REPO_ROOT / html_rel if html_rel else None
            if html_file and html_file.exists():
                html = html_file.read_text(encoding="utf-8", errors="ignore")
                pub_date, precision = extract_publication_date(url=row.get("url", ""), html=html)
        _write_page_input(
            page_id,
            row.get("url", ""),
            row.get("title", ""),
            row.get("domain", ""),
            row["markdown_path"],
            page_markdown,
            publication_date=pub_date,
            date_precision=precision or "none",
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
        markdown = md_file.read_text(encoding="utf-8")
        _write_page_input(
            entry["page_id"],
            entry.get("source_url", ""),
            entry.get("source_title", ""),
            entry.get("source_domain", ""),
            str(md_file.relative_to(REPO_ROOT)),
            markdown[:max_chars],
            publication_date=entry.get("publication_date", ""),
            date_precision=entry.get("date_precision", "none"),
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

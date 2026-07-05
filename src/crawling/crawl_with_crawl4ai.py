"""Stage 4: crawl queued frontier URLs with Crawl4AI and save clean Markdown.

Pulls queued URLs by priority, crawls with a bounded-concurrency AsyncWebCrawler,
saves markdown/html via save_markdown, appends crawl_metadata.csv rows, and marks
frontier rows crawled/failed. Requires a one-time `crawl4ai-setup` (Playwright
Chromium download) after pip install."""

import asyncio
import datetime as dt
import sys

from src.common.cli import build_parser
from src.common.columns import CRAWL_METADATA_COLUMNS
from src.common.config import CRAWLED_DIR, ensure_data_dirs, load_settings
from src.common.io_utils import append_csv_dicts, read_csv_dicts
from src.common.logging_setup import get_logger
from src.crawling.save_markdown import content_hash, detect_language, page_id_for, save_page
from src.frontier.frontier_manager import Frontier

log = get_logger("crawling.crawl_with_crawl4ai", "crawling.log")

METADATA_PATH = CRAWLED_DIR / "crawl_metadata.csv"

_BROWSER_HINT = (
    "Playwright browser not installed. Run `crawl4ai-setup` (or `playwright install "
    "chromium`) once after pip install, then rerun this stage."
)


def _extract_markdown(result) -> str:
    md = getattr(result, "markdown", None)
    if md is None:
        return ""
    if isinstance(md, str):
        return md
    return getattr(md, "fit_markdown", None) or getattr(md, "raw_markdown", None) or ""


async def _crawl_all(urls_rows, settings, save_html: bool):
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
        from crawl4ai.content_filter_strategy import PruningContentFilter
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    except ImportError as exc:
        log.error("crawl4ai not installed (pip install crawl4ai && crawl4ai-setup): %s", exc)
        sys.exit(1)

    crawler_conf = settings.crawler
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(
                min_word_threshold=int(crawler_conf.get("word_count_threshold", 20))
            )
        ),
        page_timeout=int(crawler_conf.get("page_timeout_ms", 30000)),
    )
    semaphore = asyncio.Semaphore(int(crawler_conf.get("max_concurrent", 5)))

    async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:

        async def crawl_one(row):
            async with semaphore:
                try:
                    result = await crawler.arun(url=row["url"], config=run_config)
                    return row, result, None
                except Exception as exc:  # noqa: BLE001 - per-URL isolation
                    return row, None, exc

        return await asyncio.gather(*(crawl_one(row) for row in urls_rows))


def main() -> None:
    parser = build_parser(__doc__)
    parser.add_argument("--priority", choices=["high", "medium", "all"], default="all")
    parser.add_argument("--recrawl", action="store_true", help="also crawl URLs already marked crawled")
    parser.add_argument(
        "--include-needs-review", action="store_true", help="also crawl needs_review URLs"
    )
    args = parser.parse_args()
    settings = load_settings(args.config_dir)
    ensure_data_dirs()

    statuses = ["queued"]
    if args.recrawl:
        statuses.append("crawled")
    if args.include_needs_review:
        statuses.append("needs_review")
    priorities = None if args.priority == "all" else [args.priority]
    if priorities is None:
        priorities = settings.crawler.get("crawl_priorities")

    limit = min(args.limit or settings.max_urls_to_crawl, settings.max_urls_to_crawl)
    frontier = Frontier()
    rows = [dict(r) for r in frontier.get_by_status(statuses, priorities, limit)]
    log.info("Crawling %d URLs (statuses=%s priorities=%s)", len(rows), statuses, priorities)
    if args.dry_run or not rows:
        frontier.close()
        if args.dry_run:
            log.info("[dry-run] stopping before crawling")
        return

    # content hashes of previously crawled pages, for duplicate-content labeling
    seen_hashes: set[str] = set()
    for meta in read_csv_dicts(METADATA_PATH):
        for token in (meta.get("notes") or "").split():
            if token.startswith("content_sha1="):
                seen_hashes.add(token.split("=", 1)[1])

    outcomes = asyncio.run(_crawl_all(rows, settings, settings.crawler.get("save_html", True)))

    today = dt.date.today().isoformat()
    ok = failed = 0
    for row, result, error in outcomes:
        page_id = page_id_for(row["frontier_id"])
        meta = {
            "url": row["url"],
            "normalized_url": row["normalized_url"],
            "domain": row["domain"],
            "crawl_date": today,
            "markdown_path": "",
            "html_path": "",
            "http_status": "",
            "content_type": "",
            "language": "",
            "title": "",
            "error_message": "",
            "word_count": 0,
            "char_count": 0,
            "is_duplicate_content": "false",
            "notes": "",
        }

        error_text = ""
        if error is not None:
            error_text = str(error)
        elif result is None or not getattr(result, "success", False):
            error_text = (getattr(result, "error_message", "") or "crawl failed") if result else "no result"

        markdown = _extract_markdown(result) if not error_text else ""
        if not error_text and not markdown.strip():
            error_text = "empty markdown after extraction"

        if error_text:
            if "install" in error_text.lower() and "chromium" in error_text.lower():
                log.error(_BROWSER_HINT)
            meta["crawl_status"] = "failed"
            meta["error_message"] = error_text[:500]
            frontier.mark(row["frontier_id"], "failed", error_text[:200])
            failed += 1
        else:
            html = (getattr(result, "cleaned_html", None) or "") if settings.crawler.get("save_html") else ""
            md_path, html_path = save_page(page_id, markdown, html)
            digest = content_hash(markdown)
            duplicate = digest in seen_hashes
            seen_hashes.add(digest)
            metadata = getattr(result, "metadata", None) or {}
            meta.update(
                {
                    "crawl_status": "success",
                    "http_status": getattr(result, "status_code", "") or "",
                    "content_type": "text/html",
                    "language": detect_language(markdown),
                    "title": (metadata.get("title") or "").strip(),
                    "markdown_path": md_path,
                    "html_path": html_path,
                    "word_count": len(markdown.split()),
                    "char_count": len(markdown),
                    "is_duplicate_content": str(duplicate).lower(),
                    "notes": f"content_sha1={digest}",
                }
            )
            frontier.mark(row["frontier_id"], "crawled")
            ok += 1

        append_csv_dicts(METADATA_PATH, [meta], CRAWL_METADATA_COLUMNS)

    frontier.export_csv()
    frontier.close()
    log.info("Crawl finished: %d success, %d failed. Metadata: %s", ok, failed, METADATA_PATH)


if __name__ == "__main__":
    main()

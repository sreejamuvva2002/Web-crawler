"""Backfill real publication dates for already-crawled pages.

Why a sidecar: the retained HTML is crawl4ai's *cleaned* HTML (head stripped),
so the publication meta is gone from disk. We therefore re-fetch each successful
URL's <head> to read its real published date. And because the live crawl loop may
still be appending to crawl_metadata.csv, this script does NOT rewrite that file
in place (that would race the crawler). Instead it writes a sidecar
``data/crawled/publication_dates.csv`` (url, publication_date, date_precision)
that build_page_inputs reads. Run ``--apply`` only after the crawl loop is done
to fold the sidecar into crawl_metadata.csv.

Safe to interrupt/re-run: URLs already resolved in the sidecar are skipped.
Lightweight and disk-safe: reads only the first bytes of each response, stores no
HTML.

Usage:
  python -m scripts.backfill_publication_dates [--limit N] [--force] [--apply]
"""

import argparse
import time

import requests

from src.common.columns import CRAWL_METADATA_COLUMNS
from src.common.config import CRAWLED_DIR
from src.common.io_utils import read_csv_dicts, write_csv_dicts
from src.common.logging_setup import get_logger
from src.crawling.publication_date import date_from_html, date_from_text, date_from_url

log = get_logger("crawling.backfill_publication_dates", "crawling.log")

METADATA_PATH = CRAWLED_DIR / "crawl_metadata.csv"
SIDECAR_PATH = CRAWLED_DIR / "publication_dates.csv"
SIDECAR_COLUMNS = ["url", "publication_date", "date_precision"]

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_HEAD_BYTES = 65536  # enough for <head>; we never need the body


def _fetch_head(url: str, timeout: float) -> str:
    """Return the first ~64KB of a URL's HTML, or "" on any failure."""
    try:
        with requests.get(
            url,
            headers={"User-Agent": _UA, "Accept": "text/html,*/*"},
            timeout=timeout,
            stream=True,
        ) as resp:
            if resp.status_code != 200:
                return ""
            ctype = resp.headers.get("Content-Type", "")
            if ctype and "html" not in ctype.lower():
                return ""
            chunk = resp.raw.read(_HEAD_BYTES, decode_content=True) or b""
            return chunk.decode(resp.encoding or "utf-8", errors="replace")
    except Exception as exc:  # network error, DNS, TLS, timeout, block — all fine
        log.debug("fetch failed for %s: %s", url, exc)
        return ""


def resolve_publication_date(url: str, timeout: float) -> tuple[str, str]:
    """(iso_date, precision) for one URL: HTML meta, then a visible body dateline,
    then a URL-path date."""
    html = _fetch_head(url, timeout)
    iso = date_from_html(html)
    if iso:
        return iso, "html_meta"
    iso = date_from_text(html)
    if iso:
        return iso, "body_dateline"
    iso = date_from_url(url)
    if iso:
        return iso, "url_path"
    return "", "none"


def _load_sidecar() -> dict[str, dict]:
    return {row["url"]: row for row in read_csv_dicts(SIDECAR_PATH)}


def apply_sidecar_to_metadata() -> int:
    """Fold the sidecar into crawl_metadata.csv. Run only when the crawl is done."""
    sidecar = _load_sidecar()
    rows = read_csv_dicts(METADATA_PATH)
    updated = 0
    for row in rows:
        hit = sidecar.get(row.get("url"))
        if hit and hit.get("publication_date") and not (row.get("publication_date") or "").strip():
            row["publication_date"] = hit["publication_date"]
            row["date_precision"] = hit.get("date_precision", "")
            updated += 1
    write_csv_dicts(METADATA_PATH, rows, CRAWL_METADATA_COLUMNS)
    log.info("Applied %d publication dates into %s", updated, METADATA_PATH)
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="only process the first N successful rows")
    parser.add_argument("--force", action="store_true", help="re-resolve URLs already in the sidecar")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--sleep", type=float, default=0.5, help="polite delay between fetches (s)")
    parser.add_argument("--apply", action="store_true", help="merge sidecar into crawl_metadata.csv and exit (run post-crawl)")
    args = parser.parse_args()

    if args.apply:
        apply_sidecar_to_metadata()
        return

    sidecar = _load_sidecar()
    rows = [r for r in read_csv_dicts(METADATA_PATH) if r.get("crawl_status") == "success"]
    todo = [r for r in rows if args.force or r["url"] not in sidecar]
    if args.limit:
        todo = todo[: args.limit]

    log.info("Backfilling %d URLs (%d already resolved in sidecar)", len(todo), len(sidecar))
    counts = {"html_meta": 0, "url_path": 0, "none": 0}
    for i, row in enumerate(todo, 1):
        url = row["url"]
        pub_date, precision = resolve_publication_date(url, args.timeout)
        counts[precision] = counts.get(precision, 0) + 1
        sidecar[url] = {"url": url, "publication_date": pub_date, "date_precision": precision}
        if i % 100 == 0 or i == len(todo):
            write_csv_dicts(SIDECAR_PATH, list(sidecar.values()), SIDECAR_COLUMNS)
            log.info("  %d/%d done (html_meta=%d url_path=%d none=%d)", i, len(todo), counts["html_meta"], counts["url_path"], counts["none"])
        if args.sleep:
            time.sleep(args.sleep)

    write_csv_dicts(SIDECAR_PATH, list(sidecar.values()), SIDECAR_COLUMNS)
    log.info(
        "Done: %d resolved via html_meta, %d via url_path, %d undated -> %s",
        counts["html_meta"], counts["url_path"], counts["none"], SIDECAR_PATH,
    )


if __name__ == "__main__":
    main()

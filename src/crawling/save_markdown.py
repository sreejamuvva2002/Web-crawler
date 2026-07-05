"""Stage 4 helpers: deterministic page ids/paths, saving markdown+html, language
detection, and content hashing for duplicate-content labeling.

page ids derive from frontier_id (page_000123), so re-crawling a URL overwrites
the same files instead of accumulating copies (idempotent, spec Rule 6)."""

import hashlib
import re
from pathlib import Path

from src.common.config import HTML_DIR, MARKDOWN_DIR


def page_id_for(frontier_id: int) -> str:
    return f"page_{int(frontier_id):06d}"


def markdown_path_for(page_id: str) -> Path:
    return MARKDOWN_DIR / f"{page_id}.md"


def html_path_for(page_id: str) -> Path:
    return HTML_DIR / f"{page_id}.html"


def save_page(page_id: str, markdown: str, html: str | None = None) -> tuple[str, str]:
    """Write the page files; returns (markdown_path, html_path) as repo-relative
    strings for crawl_metadata.csv ('' when not saved)."""
    md_path = markdown_path_for(page_id)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")
    rel_md = f"data/crawled/markdown/{page_id}.md"

    rel_html = ""
    if html:
        h_path = html_path_for(page_id)
        h_path.parent.mkdir(parents=True, exist_ok=True)
        h_path.write_text(html, encoding="utf-8")
        rel_html = f"data/crawled/html/{page_id}.html"
    return rel_md, rel_html


def detect_language(text: str) -> str:
    try:
        from langdetect import detect

        return detect(text[:2000])
    except Exception:  # noqa: BLE001 - langdetect raises on empty/ambiguous text
        return "unknown"


def content_hash(markdown: str) -> str:
    """Whitespace-normalized sha1, used to label duplicate page content."""
    normalized = re.sub(r"\s+", " ", markdown).strip().casefold()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

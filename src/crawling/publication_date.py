"""Publication-date extraction, shared by the live crawler and the backfill
script.

Priority order for the source page's real publication date:
  1. HTML/metadata publication tags (article:published_time, og:published_time,
     JSON-LD datePublished, <meta name=date>, <time datetime>)  -> precision "html_meta"
  2. a visible news dateline or "Published/Posted: <date>" label in the page body
     (e.g. `ATLANTA - May 15, 2023`, `Published">June 05, 2025`)  -> precision "body_dateline"
  3. a YYYY-MM-DD date embedded in the URL path                  -> precision "url_path"
  4. a YYYY/MM (year + month, no day) segment in the URL path    -> precision "url_path_month"
  5. nothing                                                     -> precision "none"

Everything returns an ISO ``YYYY-MM-DD`` string (or "") plus a precision tag so
downstream currency logic and the answer layer can tell an exact date from a
coarse URL-derived one. Regex-only, no bs4/lxml dependency."""

import re

# ISO-ish date anywhere in a string: full date preferred, else year-month, else year.
_FULL_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_YEAR_MONTH = re.compile(r"(\d{4})-(\d{2})(?!\d)")
_YEAR = re.compile(r"(?<!\d)(\d{4})(?!\d)")

# YYYY-MM-DD or YYYY/MM/DD as a URL path segment (e.g. /press-releases/2023-01-30/...).
_URL_DATE = re.compile(r"/(20\d\d)[-/](\d{2})[-/](\d{2})(?:[/?#.]|$)")
# YYYY/MM (year + month, no day) as a URL path segment (e.g. /2022/11/story-slug).
_URL_MONTH = re.compile(r"/(20\d\d)/(\d{2})(?:[/?#]|$)")

# HTML <head> publication signals, in descending trust order.
_META_PATTERNS = [
    re.compile(r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:published_time["\']', re.I),
    re.compile(r'<meta[^>]+property=["\']og:published_time["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+itemprop=["\']datePublished["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'"datePublished"\s*:\s*"([^"]+)"', re.I),
    re.compile(r'<meta[^>]+name=["\'](?:date|pubdate|publishdate|publish-date|publication_date|dc\.date)["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<time[^>]+datetime=["\']([^"\']+)["\']', re.I),
]

# crawl4ai already parses the <head> into result.metadata; these are the keys it
# (or a similar extractor) exposes a publication date under.
_METADATA_KEYS = (
    "article:published_time",
    "og:published_time",
    "published_time",
    "publishedtime",
    "datepublished",
    "date",
    "pubdate",
    "publishdate",
    "dc.date",
)


def normalize_iso(raw: str) -> str:
    """Reduce a raw date/datetime string to ISO ``YYYY-MM-DD`` (best effort).

    Pads year-only -> YYYY-01-01 and year-month -> YYYY-MM-01 so partial dates
    still sort and bucket. Returns "" if no plausible year is found."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    m = _FULL_DATE.search(raw)
    if m:
        year, month, day = m.groups()
        if "01" <= month <= "12" and "01" <= day <= "31":
            return f"{year}-{month}-{day}"
    m = _YEAR_MONTH.search(raw)
    if m and "01" <= m.group(2) <= "12":
        return f"{m.group(1)}-{m.group(2)}-01"
    m = _YEAR.search(raw)
    if m and "1990" <= m.group(1) <= "2099":
        return f"{m.group(1)}-01-01"
    return ""


def date_from_metadata(metadata: dict) -> str:
    """Publication date from a crawl4ai-style metadata dict (already head-parsed)."""
    if not metadata:
        return ""
    lowered = {str(k).strip().casefold(): v for k, v in metadata.items()}
    for key in _METADATA_KEYS:
        iso = normalize_iso(str(lowered.get(key) or ""))
        if iso:
            return iso
    return ""


def date_from_html(html: str) -> str:
    """Publication date parsed out of raw HTML <head> tags / JSON-LD."""
    if not html:
        return ""
    for pattern in _META_PATTERNS:
        m = pattern.search(html)
        if m:
            iso = normalize_iso(m.group(1))
            if iso:
                return iso
    return ""


_MONTH_NUM = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}
# A news dateline date immediately after a dash: "ATLANTA – May 15, 2023".
_DATELINE_RE = re.compile(r"[–—-]\s*([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s+(\d{4})")
# Any "Month DD, YYYY" (looser fallback, restricted to the head of the page).
_LOOSE_DATE_RE = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s+(\d{4})\b")


def _month_date_iso(name: str, day: str, year: str) -> str:
    month = _MONTH_NUM.get(name.strip(".").casefold())
    if not month:
        return ""
    d = int(day)
    if not (1 <= d <= 31) or not ("1990" <= year <= "2099"):
        return ""
    return f"{year}-{month:02d}-{d:02d}"


def date_from_text(text: str) -> str:
    """Publication date from a visible article dateline / "Month DD, YYYY" near the
    top of the page body (e.g. "ATLANTA – May 15, 2023"). Restricted to the head so
    a random date deeper in the article isn't mistaken for the publication date."""
    if not text:
        return ""
    head = text[:2000]
    for pattern in (_DATELINE_RE, _LOOSE_DATE_RE):
        m = pattern.search(head)
        if m:
            iso = _month_date_iso(*m.groups())
            if iso:
                return iso
    return ""


# A "Published"/"Posted" (never "Updated") publication label, whose date follows
# within a short window. Scanned over the WHOLE HTML, not just the head, because
# these visible body datelines live outside <head> meta and get stripped from the
# trafilatura markdown — e.g. `<span aria-label="Published">June 05, 2025</span>`.
_PUB_LABEL_RE = re.compile(
    r"(?:date\s*published|published\s*(?:on|date)?|posted\s*(?:on)?|release\s*date)",
    re.I,
)
_TAG_RE = re.compile(r"<[^>]+>")
# An ISO date embedded in a short text window (e.g. datetime='2025-06-05').
_ISO_IN_TEXT = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
# Text content of a <time> element with no datetime attribute, e.g.
# `<time>May 20, 2022</time>` (Elementor/WordPress post-date widgets).
_TIME_TEXT_RE = re.compile(r"<time[^>]*>([^<]{4,40})</time>", re.I)


def _date_from_window(window: str) -> str:
    """First ``Month DD, YYYY`` or ISO ``YYYY-MM-DD`` date in a short text window."""
    dm = _LOOSE_DATE_RE.search(window)
    if dm:
        iso = _month_date_iso(*dm.groups())
        if iso:
            return iso
    im = _ISO_IN_TEXT.search(window)
    if im:
        iso = normalize_iso(im.group(0))
        if iso:
            return iso
    return ""


def date_from_labeled_html(html: str) -> str:
    """Publication date from a visible "Published"/"Posted" label or a bare
    ``<time>`` element anywhere in the HTML body. Handles dates that sit past the
    first 2000 chars and that trafilatura strips from the markdown, e.g.
    ``...Published">June 05, 2025...`` or ``<time>May 20, 2022</time>``.

    For each publish label, the next ~120 chars (tags removed) are scanned for a
    ``Month DD, YYYY`` or ISO ``YYYY-MM-DD`` date; bare ``<time>`` text is parsed
    directly."""
    if not html:
        return ""
    for m in _PUB_LABEL_RE.finditer(html):
        iso = _date_from_window(_TAG_RE.sub(" ", html[m.end(): m.end() + 120]))
        if iso:
            return iso
    for m in _TIME_TEXT_RE.finditer(html):
        iso = _date_from_window(m.group(1))
        if iso:
            return iso
    return ""


def date_from_url(url: str) -> str:
    """Publication date from a YYYY-MM-DD / YYYY/MM/DD path segment in the URL."""
    m = _URL_DATE.search(url or "")
    if not m:
        return ""
    year, month, day = m.groups()
    if "01" <= month <= "12" and "01" <= day <= "31":
        return f"{year}-{month}-{day}"
    return ""


def date_from_url_month(url: str) -> str:
    """Coarse ``YYYY-MM`` from a year/month URL segment (e.g. /2022/11/slug), when no
    full date is present. Returns ``YYYY-MM`` (no day) to signal month precision."""
    m = _URL_MONTH.search(url or "")
    if not m:
        return ""
    year, month = m.groups()
    if "01" <= month <= "12":
        return f"{year}-{month}"
    return ""


def extract_publication_date(
    url: str = "",
    metadata: dict | None = None,
    html: str = "",
) -> tuple[str, str]:
    """Return ``(iso_date, precision)`` from the best available signal.

    precision is one of ``html_meta`` / ``body_dateline`` / ``url_path`` /
    ``url_path_month`` / ``none``."""
    iso = date_from_metadata(metadata or {}) or date_from_html(html)
    if iso:
        return iso, "html_meta"
    iso = date_from_text(html) or date_from_labeled_html(html)
    if iso:
        return iso, "body_dateline"
    iso = date_from_url(url)
    if iso:
        return iso, "url_path"
    iso = date_from_url_month(url)
    if iso:
        return iso, "url_path_month"
    return "", "none"

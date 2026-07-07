"""Canonical CSV column orders (from the spec) shared across stages."""

QUERY_COLUMNS = ["query", "source_type", "iteration", "status"]

URL_CANDIDATE_COLUMNS = [
    "url",
    "normalized_url",
    "domain",
    "title",
    "snippet",
    "query_used",
    "search_engine",
    "rank",
    "discovered_date",
    "source_type",
    "status",
    "notes",
]

FRONTIER_COLUMNS = [
    "frontier_id",
    "url",
    "normalized_url",
    "domain",
    "priority",
    "status",
    "discovered_from",
    "query_used",
    "first_seen_date",
    "last_checked_date",
    "retry_count",
    "crawl_error",
    "notes",
]

FRONTIER_STATUSES = ["new", "queued", "crawled", "failed", "duplicate", "rejected", "needs_review"]

CRAWL_METADATA_COLUMNS = [
    "url",
    "normalized_url",
    "domain",
    "crawl_status",
    "http_status",
    "content_type",
    "language",
    "title",
    "markdown_path",
    "html_path",
    "crawl_date",
    "error_message",
    "word_count",
    "char_count",
    "is_duplicate_content",
    "notes",
]
# NOTE: publication_date / date_precision are intentionally NOT added here yet.
# The crawl loop is live and its in-flight batch uses the 16-column schema; adding
# columns mid-run corrupts crawl_metadata.csv. The crawler already extracts the
# publication date (crawl_with_crawl4ai.py) but append_csv_dicts drops those keys
# via extrasaction="ignore" until these two columns are re-added during a clean,
# fully-stopped crawl restart. Until then, publication dates reach Stage 5 via the
# backfill sidecar (data/crawled/publication_dates.csv).

DOMAIN_SUMMARY_COLUMNS = ["domain", "url_count", "priority", "sample_titles"]

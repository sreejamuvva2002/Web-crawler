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

DOMAIN_SUMMARY_COLUMNS = ["domain", "url_count", "priority", "sample_titles"]

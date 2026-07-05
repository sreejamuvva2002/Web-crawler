"""Firecrawl search provider (optional; needs FIRECRAWL_API_KEY). Used only for
URL discovery — Crawl4AI remains the crawling/extraction stage."""

from src.common.config import Settings
from src.discovery.provider_base import ProviderError, SearchProvider, SearchResult


class FirecrawlProvider(SearchProvider):
    name = "firecrawl"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        if not settings.firecrawl_api_key:
            raise ProviderError("Firecrawl enabled but FIRECRAWL_API_KEY is not set.")
        try:
            from firecrawl import FirecrawlApp
        except ImportError as exc:
            raise ProviderError("firecrawl-py not installed (pip install firecrawl-py).") from exc
        self.app = FirecrawlApp(api_key=settings.firecrawl_api_key)

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        response = self.app.search(query, limit=max_results)
        # firecrawl-py returns a dict or a pydantic object depending on version
        items = response.get("data", []) if isinstance(response, dict) else getattr(response, "data", [])
        results = []
        for i, item in enumerate(items[:max_results], start=1):
            get = item.get if isinstance(item, dict) else lambda k, d="": getattr(item, k, d)
            url = get("url") or ""
            if not url:
                continue
            results.append(
                SearchResult(
                    title=get("title", "") or "",
                    url=url,
                    snippet=get("description", "") or "",
                    rank=i,
                    engine=self.name,
                    query=query,
                )
            )
        return results

"""Tavily provider (optional; needs TAVILY_API_KEY). Higher-quality AI-oriented
search fallback — avoid running every query through it if credits are limited."""

from src.common.config import Settings
from src.discovery.provider_base import ProviderError, SearchProvider, SearchResult


class TavilyProvider(SearchProvider):
    name = "tavily"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        if not settings.tavily_api_key:
            raise ProviderError("Tavily enabled but TAVILY_API_KEY is not set.")
        try:
            from tavily import TavilyClient
        except ImportError as exc:
            raise ProviderError("tavily-python not installed (pip install tavily-python).") from exc
        self.client = TavilyClient(api_key=settings.tavily_api_key)

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        response = self.client.search(query=query, max_results=max_results)
        results = []
        for i, item in enumerate(response.get("results", []), start=1):
            url = item.get("url") or ""
            if not url:
                continue
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=url,
                    snippet=item.get("content", ""),
                    rank=i,
                    engine=self.name,
                    query=query,
                )
            )
        return results

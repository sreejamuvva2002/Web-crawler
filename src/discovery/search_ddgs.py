"""DDGS provider (optional; disabled by default — results can be unstable and
rate-limited). Enable via DDGS_ENABLED=true or configs/search_config.yaml."""

from src.common.config import Settings
from src.discovery.provider_base import ProviderError, SearchProvider, SearchResult


class DdgsProvider(SearchProvider):
    name = "ddgs"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        try:
            from ddgs import DDGS
        except ImportError as exc:
            raise ProviderError("ddgs package not installed (pip install ddgs).") from exc
        self._ddgs_cls = DDGS

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        with self._ddgs_cls() as ddgs:
            hits = list(ddgs.text(query, max_results=max_results))
        results = []
        for i, hit in enumerate(hits, start=1):
            url = hit.get("href") or hit.get("url") or ""
            if not url:
                continue
            results.append(
                SearchResult(
                    title=hit.get("title", ""),
                    url=url,
                    snippet=hit.get("body", ""),
                    rank=i,
                    engine=self.name,
                    query=query,
                )
            )
        return results

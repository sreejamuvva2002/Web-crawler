"""Search provider interface. collect_urls talks only to SearchProvider; each
provider module implements one class. Providers are lazily imported so a missing
optional dependency (e.g. tavily-python) never breaks a SearXNG-only run."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.common.config import FIXTURES_DIR, Settings


class ProviderError(RuntimeError):
    """Provider unusable (bad config, unreachable endpoint). Aborts the stage."""


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    rank: int
    engine: str
    query: str


class SearchProvider(ABC):
    name: str = "base"

    def __init__(self, settings: Settings):
        self.settings = settings

    def health_check(self) -> None:
        """Raise ProviderError if the provider cannot serve queries."""

    @abstractmethod
    def search(self, query: str, max_results: int) -> list[SearchResult]: ...


class MockSearchProvider(SearchProvider):
    """Fixture-backed provider for offline runs (SEARCH_MOCK=true). Returns the
    same fixture results for every query, which also exercises deduplication."""

    name = "mock"
    fixture_path = FIXTURES_DIR / "sample_search_results.json"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        if not self.fixture_path.exists():
            raise ProviderError(f"Mock fixtures missing: {self.fixture_path}")
        with open(self.fixture_path) as f:
            self._results = json.load(f)["results"]

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r["url"],
                snippet=r.get("snippet", ""),
                rank=i,
                engine=self.name,
                query=query,
            )
            for i, r in enumerate(self._results[:max_results], start=1)
        ]


def get_enabled_providers(settings: Settings) -> list[SearchProvider]:
    if settings.search_mock:
        return [MockSearchProvider(settings)]

    conf = settings.search.get("providers", {})
    providers: list[SearchProvider] = []

    if conf.get("mock", {}).get("enabled"):
        providers.append(MockSearchProvider(settings))
    if conf.get("searxng", {}).get("enabled"):
        from src.discovery.search_searxng import SearxngProvider

        providers.append(SearxngProvider(settings))
    if conf.get("ddgs", {}).get("enabled") or settings.ddgs_enabled:
        from src.discovery.search_ddgs import DdgsProvider

        providers.append(DdgsProvider(settings))
    if conf.get("tavily", {}).get("enabled"):
        from src.discovery.search_tavily import TavilyProvider

        providers.append(TavilyProvider(settings))
    if conf.get("firecrawl", {}).get("enabled"):
        from src.discovery.search_firecrawl import FirecrawlProvider

        providers.append(FirecrawlProvider(settings))

    if not providers:
        raise ProviderError(
            "No search providers enabled. Enable one in configs/search_config.yaml "
            "or set SEARCH_MOCK=true for an offline run."
        )
    return providers

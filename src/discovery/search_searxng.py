"""SearXNG metasearch provider (primary). GET {SEARXNG_URL}/search?format=json.

The instance must have the JSON format enabled in its settings.yml
(search: formats: [html, json]) or every request returns HTTP 403.
"""

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.common.config import Settings
from src.discovery.provider_base import ProviderError, SearchProvider, SearchResult

_403_HINT = (
    "SearXNG returned 403 for format=json. Enable the JSON format on the instance: "
    "in its settings.yml set  search: formats: [html, json]  and restart SearXNG."
)


class SearxngProvider(SearchProvider):
    name = "searxng"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        if not settings.searxng_url:
            raise ProviderError("SEARXNG_URL is not set (see .env.example).")
        self.base_url = settings.searxng_url
        conf = settings.search.get("providers", {}).get("searxng", {})
        self.engines = conf.get("engines")
        self.categories = conf.get("categories", "general")
        self.language = settings.search.get("language", "en")
        self.session = requests.Session()

    def health_check(self) -> None:
        try:
            resp = self.session.get(
                f"{self.base_url}/search", params={"q": "test", "format": "json"}, timeout=15
            )
        except requests.RequestException as exc:
            raise ProviderError(
                f"SearXNG unreachable at {self.base_url} — is the instance running? ({exc})"
            ) from exc
        if resp.status_code == 403:
            raise ProviderError(_403_HINT)
        if resp.status_code >= 400:
            raise ProviderError(f"SearXNG health check failed: HTTP {resp.status_code}")

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        reraise=True,
    )
    def _get(self, params: dict) -> dict:
        resp = self.session.get(f"{self.base_url}/search", params=params, timeout=30)
        if resp.status_code == 403:
            raise ProviderError(_403_HINT)
        resp.raise_for_status()
        return resp.json()

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        params = {"q": query, "format": "json", "language": self.language, "pageno": 1}
        if self.categories:
            params["categories"] = self.categories
        if self.engines:
            params["engines"] = self.engines
        data = self._get(params)

        results = []
        for i, item in enumerate(data.get("results", [])[:max_results], start=1):
            url = (item.get("url") or "").strip()
            if not url:
                continue
            results.append(
                SearchResult(
                    title=(item.get("title") or "").strip(),
                    url=url,
                    snippet=(item.get("content") or "").strip(),
                    rank=i,
                    engine=self.name,
                    query=query,
                )
            )
        return results

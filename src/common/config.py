"""Settings loading: .env + configs/*.yaml merged into one Settings object.

Env vars override YAML values where they overlap. All stages call load_settings()
once at startup and read everything from the returned object.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
URLS_DIR = DATA_DIR / "urls"
CRAWLED_DIR = DATA_DIR / "crawled"
MARKDOWN_DIR = CRAWLED_DIR / "markdown"
HTML_DIR = CRAWLED_DIR / "html"
WIKI_DIR = DATA_DIR / "wiki"
PAGE_INPUTS_DIR = WIKI_DIR / "page_inputs"
EXPORTS_DIR = DATA_DIR / "exports"
LOGS_DIR = REPO_ROOT / "logs"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


@dataclass
class Settings:
    config_dir: Path
    # YAML configs
    search: dict
    query_templates: dict
    domain_priority: dict
    crawler: dict
    wiki_schema: dict
    llm: dict
    # env-derived
    searxng_url: str
    tavily_api_key: str
    firecrawl_api_key: str
    ddgs_enabled: bool
    qwen_model: str
    llm_base_url: str
    llm_api_key: str
    max_results_per_query: int
    max_discovery_iterations: int
    max_urls_to_crawl: int
    search_mock: bool
    llm_mock: bool


def load_settings(config_dir: str | Path | None = None) -> Settings:
    load_dotenv(REPO_ROOT / ".env")
    cdir = Path(config_dir) if config_dir else REPO_ROOT / "configs"

    search = _load_yaml(cdir / "search_config.yaml")
    settings = Settings(
        config_dir=cdir,
        search=search,
        query_templates=_load_yaml(cdir / "query_templates.yaml"),
        domain_priority=_load_yaml(cdir / "domain_priority.yaml"),
        crawler=_load_yaml(cdir / "crawler_config.yaml"),
        wiki_schema=_load_yaml(cdir / "wiki_schema.yaml"),
        llm=_load_yaml(cdir / "llm_config.yaml"),
        searxng_url=os.environ.get("SEARXNG_URL", "").rstrip("/"),
        tavily_api_key=os.environ.get("TAVILY_API_KEY", ""),
        firecrawl_api_key=os.environ.get("FIRECRAWL_API_KEY", ""),
        ddgs_enabled=_env_bool("DDGS_ENABLED"),
        qwen_model=os.environ.get("QWEN_MODEL", "Qwen/Qwen3-235B-A22B-Instruct-2507"),
        llm_base_url=os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1"),
        llm_api_key=os.environ.get("LLM_API_KEY", "dummy"),
        max_results_per_query=_env_int(
            "MAX_RESULTS_PER_QUERY", int(search.get("max_results_per_query", 10))
        ),
        max_discovery_iterations=_env_int("MAX_DISCOVERY_ITERATIONS", 3),
        max_urls_to_crawl=_env_int("MAX_URLS_TO_CRAWL", 1000),
        search_mock=_env_bool("SEARCH_MOCK"),
        llm_mock=_env_bool("LLM_MOCK"),
    )
    return settings


def ensure_data_dirs() -> None:
    for d in (INPUT_DIR, URLS_DIR, MARKDOWN_DIR, HTML_DIR, PAGE_INPUTS_DIR, EXPORTS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)

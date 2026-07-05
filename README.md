# Georgia EV Web Data Discovery and LLM Wiki Pipeline

A source-backed web-data pipeline for discovering, collecting, crawling, and converting
Georgia electric-vehicle supply-chain web information into an LLM Wiki.

```
URL discovery
→ URL deduplication and frontier management
→ iterative URL expansion
→ Crawl4AI page crawling and Markdown extraction
→ Qwen 235B LLM Wiki generation
→ validation and export
```

Crawl4AI produces clean source documents. Qwen3-235B-A22B-Instruct reads those documents
and generates structured, source-backed wiki records. Pydantic/Instructor validation
filters unsupported records. Every fact in the final wiki keeps its `source_url` and
`evidence_text`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
crawl4ai-setup            # one-time: installs the Playwright Chromium browser (~150 MB)
cp .env.example .env      # then fill in SEARXNG_URL / LLM_BASE_URL etc.
```

Required services:

- **SearXNG** (primary search provider): a self-hosted instance reachable at `SEARXNG_URL`.
  The instance must have the JSON output format enabled — in its `settings.yml`:
  `search: formats: [html, json]` — otherwise every query returns HTTP 403.
  Note: `site:` queries only work through upstream engines that support them (google, bing).
- **vLLM** serving Qwen 235B (wiki-generation stages): an OpenAI-compatible endpoint at
  `LLM_BASE_URL`. Any OpenAI-compatible server works; the model name comes from `QWEN_MODEL`.

Offline modes: set `SEARCH_MOCK=true` to use fixture search results, and pass `--mock-llm`
(or `LLM_MOCK=true`) to the wiki-generation scripts to use canned LLM output. The whole
pipeline can run without network for testing.

## Running the pipeline

All scripts run as modules from the repo root and accept `--config-dir`, `--limit`, `--dry-run`.

```bash
# Stage 1: URL discovery
python -m src.discovery.generate_queries
python -m src.discovery.collect_urls

# Stage 2: normalize, dedupe, prioritize, frontier
python -m src.url_processing.normalize_urls
python -m src.url_processing.deduplicate_urls
python -m src.url_processing.build_domain_summary
python -m src.url_processing.prioritize_urls
python -m src.frontier.update_frontier

# Stage 3: iterative expansion (repeat with --iteration 2, 3; capped at MAX_DISCOVERY_ITERATIONS)
python -m src.expansion.extract_entities_for_expansion --iteration 1
python -m src.expansion.generate_followup_queries --iteration 1
python -m src.expansion.merge_new_queries --iteration 1
python -m src.discovery.collect_urls --iteration 1
# ... then rerun the stage-2 scripts (all idempotent)

# Stage 4: crawl
python -m src.crawling.crawl_with_crawl4ai
python -m src.crawling.crawl_status_report

# Stage 5: page-level wiki records
python -m src.wiki_generation.build_page_inputs
python -m src.wiki_generation.generate_page_wiki_records
python -m src.wiki_generation.validate_page_records

# Stage 6: entity-level wiki
python -m src.wiki_generation.group_records_by_entity
python -m src.wiki_generation.generate_entity_wiki

# Stage 7: validate + export
python -m src.validation.check_source_grounding
python -m src.validation.remove_duplicate_facts
python -m src.export.export_final_wiki
python -m src.export.export_sources

# Optional: fine-tuning dataset (validated entities only)
python -m src.export.export_finetuning_data
```

Every stage writes its outputs to disk and is restartable: rerunning a stage skips or
overwrites deterministically, never duplicates.

## Repository layout

- `configs/` — search providers, query templates, domain priorities, crawler, wiki schema, LLM.
- `data/input/` — seed queries / domains / companies / locations (CSV).
- `data/urls/` — discovered URL candidates, frontier (`frontier.db` is the source of truth;
  `url_frontier.csv` is re-exported after each mutating stage).
- `data/crawled/` — Markdown + HTML per page, `crawl_metadata.csv`.
- `data/wiki/` — page inputs, raw/validated/failed wiki records, entity groups, entity wikis.
- `data/exports/` — final wiki, sources, URL inventory, fine-tuning candidates.
- `src/` — one package per stage; `src/common/` holds shared config/logging/IO/URL utilities.
- `notebooks/` — review notebooks for URL candidates, domain coverage, crawled pages, final wiki.

## Rules the pipeline enforces

1. Search snippets are not facts — they only feed URL discovery and query expansion.
2. Crawl4AI does not create the final wiki — Qwen does, from crawled Markdown.
3. No giant single-prompt wiki: page-level records → validation → entity-level merge.
4. Every fact needs a source; records without `source_url` + `evidence_text` are rejected.
5. Uncertain URLs are labeled (`needs_review`, `rejected`), never deleted.
6. Every stage is restartable from disk.
7. Raw LLM output never goes directly into the final wiki.

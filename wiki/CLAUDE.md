# Wiki schema & conventions

This file configures any LLM agent maintaining the Georgia EV Supply-Chain wiki in this
directory. Read it before ingesting sources, answering queries, or linting. Co-evolve it as
conventions change.

## Scope

The wiki covers the **electric-vehicle supply chain in Georgia (USA)**: battery cell and
materials makers, vehicle assembly, components, charging infrastructure, recycling, plus the
government programs, incentives, workforce initiatives, people, and events around them.

## Layers (never blur them)

- **Raw sources** — `../data/crawled/markdown/*.md` (Crawl4AI output) and the distilled,
  source-grounded records in `../data/wiki/wiki_records_validated.jsonl`. **Read-only.**
- **This wiki** — the markdown you maintain here. You own it entirely.
- **This schema** — the rules below.

## Page types & locations

| Type      | Path                     | One per…                    | Owner              |
| --------- | ------------------------ | --------------------------- | ------------------ |
| Entity    | `entities/<slug>.md`     | canonical company/JV/program/facility | generator |
| Concept   | `concepts/<slug>.md`     | supply-chain segment        | generator          |
| Geography | `geography/county-<slug>.md` | Georgia county          | generator          |
| Index     | `index.md`               | the wiki (catalog)          | generator          |
| Log       | `log.md`                 | the wiki (timeline)         | generator/agent    |
| Overview  | `overview.md`            | the wiki (high-level map)   | **agent, by hand** |
| Synthesis | `synthesis.md`           | the wiki (the thesis)       | **agent, by hand** |

**Generated pages** (`entities/`, `concepts/`, `geography/`, `index.md`) are produced by
`scripts/build_llm_wiki.py`. Do not hand-edit them for facts that live in the records — fix
the record or the generator and rerun. Hand-edit only the narrative pages.

## Conventions

- **Slugs** are lowercase, hyphenated, from the canonical name (`SK Battery America` →
  `sk-battery-america`). Entity links use the slug directly; concept/county links use the
  category slug / `county-<slug>`.
- **Wikilinks** use `[[slug|Display Name]]`. Link liberally: every entity page links to its
  concept and county pages; related organizations that are themselves entities get linked.
- **Frontmatter** (YAML) on every page: `title`, `entity_type`/`page_type`,
  `supply_chain_category`, `county`, `sources`, `tags`. Keep it Dataview-queryable.
- **Every fact is sourced.** Entity pages end with a `## Sources` list of `source_url`s. Never
  state a fact the records don't support. If you add a claim from a web search during a query,
  cite it inline.
- **Categories** (the `supply_chain_category` vocabulary): `battery_materials`,
  `battery_cell_manufacturing`, `battery_recycling`, `vehicle_manufacturing`,
  `automotive_components`, `power_electronics`, `thermal_management`,
  `charging_infrastructure`, `government_support`, `workforce_training`,
  `research_and_development`, `logistics`, `unknown`.

## Workflows

### Ingest (new source)
1. Read the raw markdown (and, if present, its validated record).
2. Identify the canonical entity. Update or create `entities/<slug>.md`; merge facilities,
   investment, jobs, timeline, key facts, and sources — don't duplicate.
3. Update the entity's concept and county pages if membership changed.
4. Re-run `scripts/build_llm_wiki.py` if the source is already in the validated records, or
   hand-edit for one-off sources.
5. Refresh `overview.md`/`synthesis.md` if the source changes the big picture.
6. Append a `## [YYYY-MM-DD] ingest | <title>` entry to `log.md`.

### Query
1. Read `index.md`, then `overview.md`, to locate relevant pages.
2. Drill into entity/concept/geography pages; synthesize a **cited** answer.
3. If the answer is reusable (a comparison, a ranking, a cross-cut), file it as a new page and
   link it from `index.md`. Log it.

### Lint
Check for: contradictions between pages, stale claims superseded by newer sources, orphan
pages (no inbound links), concepts mentioned but lacking a page, missing cross-references, and
data gaps a web search could fill. Record findings in `log.md`.

## Log entry format

`## [YYYY-MM-DD] <op> | <short title>` where `<op>` ∈ `ingest | build | query | lint`.
Keeps the log greppable: `grep '^## \[' log.md | tail`.

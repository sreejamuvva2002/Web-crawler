# LLM Wiki — Georgia EV Supply Chain

This directory is a **persistent, LLM-maintained knowledge base** built on top of the
crawled sources in this repo. It is an instantiation of the *LLM Wiki* pattern (the full
idea is preserved below). Where a RAG system re-derives knowledge from raw documents on
every query, this wiki **compiles knowledge once and keeps it current**: an interlinked
set of markdown pages that sits between you and the ~30,000 crawled markdown files in
`data/crawled/markdown/`.

## What's here

```
wiki/
├── README.md      ← you are here — the idea + how this vault is organized
├── CLAUDE.md      ← the schema: conventions + workflows for maintaining the wiki
├── index.md       ← content catalog (every page, one line each)  [generated]
├── log.md         ← append-only chronological record of operations  [generated]
├── overview.md    ← hand-written high-level picture of the corpus
├── synthesis.md   ← the evolving thesis: what the sources add up to
├── entities/      ← one page per company / JV / program / facility  [generated]
├── concepts/      ← one page per supply-chain segment  [generated]
└── geography/     ← one page per Georgia county  [generated]
```

Open this folder in **Obsidian** to browse it as intended: `[[wikilinks]]` are clickable,
the graph view shows how entities connect, and Dataview can query the YAML frontmatter on
each page.

## The three layers (as applied here)

1. **Raw sources** — `data/crawled/markdown/*.md`. Immutable Crawl4AI output. The source of
   truth. The wiki never modifies these.
2. **The wiki** — this directory. LLM-generated, interlinked markdown. Every fact keeps its
   `source_url` + `evidence_text`, so claims are traceable back to layer 1.
3. **The schema** — [`CLAUDE.md`](CLAUDE.md). Tells the LLM how the wiki is structured and
   what workflows to follow when ingesting, querying, or linting.

## How this vault is built

Because the pipeline already distilled the crawled pages into **source-grounded, validated
records** (`data/wiki/wiki_records_validated.jsonl`), the "ingest" step here is run in batch
over the whole corpus rather than one source at a time. The generator is reproducible and
idempotent:

```bash
python scripts/build_llm_wiki.py
```

It merges the 480 validated records into ~250 canonical entity pages plus concept and
geography pages, and regenerates `index.md` and appends to `log.md`. The narrative pages
(`overview.md`, `synthesis.md`) are hand-maintained and never overwritten — that's where an
agent does the real synthesis work described in the pattern.

---

# The pattern (source idea)

> The following is the general *LLM Wiki* idea this vault instantiates, kept for reference.

Most people's experience with LLMs and documents looks like RAG: you upload a collection of
files, the LLM retrieves relevant chunks at query time, and generates an answer. This works,
but the LLM is rediscovering knowledge from scratch on every question. There's no
accumulation.

The idea here is different. Instead of just retrieving from raw documents at query time, the
LLM incrementally builds and maintains a persistent wiki — a structured, interlinked
collection of markdown files that sits between you and the raw sources. When you add a new
source, the LLM reads it, extracts the key information, and integrates it into the existing
wiki — updating entity pages, revising topic summaries, noting where new data contradicts
old claims. The knowledge is compiled once and then kept current, not re-derived on every
query.

**The human's job** is to curate sources, direct the analysis, ask good questions, and think
about what it all means. **The LLM's job** is everything else: summarizing, cross-referencing,
filing, and the bookkeeping that makes a knowledge base useful over time.

### Operations

- **Ingest.** Drop a new source into the raw collection and tell the LLM to process it. It
  reads the source, writes/updates entity and concept pages, refreshes the index, and appends
  to the log. A single source might touch 10–15 pages.
- **Query.** Ask questions against the wiki. The LLM reads the index, drills into relevant
  pages, and synthesizes a cited answer. Good answers get filed back as new pages so
  explorations compound.
- **Lint.** Periodically health-check the wiki: contradictions, stale claims, orphan pages,
  missing cross-references, concepts that deserve their own page, data gaps to fill.

### Indexing and logging

- **`index.md`** is content-oriented: a catalog of every page with a one-line summary,
  organized by category. Read it first when answering a query, then drill in.
- **`log.md`** is chronological: an append-only record of ingests, queries, and lint passes.
  Consistent entry prefixes (`## [YYYY-MM-DD] op | title`) keep it greppable.

### Why it works

The tedious part of a knowledge base isn't the reading or thinking — it's the bookkeeping:
updating cross-references, keeping summaries current, flagging contradictions across dozens of
pages. Humans abandon wikis because the maintenance burden grows faster than the value. LLMs
don't get bored and can touch 15 files in one pass, so the wiki stays maintained because the
cost of maintenance is near zero. The idea is close in spirit to Vannevar Bush's Memex
(1945) — a private, curated knowledge store with associative trails between documents — with
the LLM finally solving the part Bush couldn't: who does the maintenance.

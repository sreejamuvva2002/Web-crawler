"""Stage 3: extract company/location entities from discovered titles and snippets
(and crawl-metadata titles once crawling has run) to seed follow-up queries.

Deterministic heuristics only — no LLM. Snippets feed queries, never wiki
records (spec Rule 1)."""

import re
from collections import Counter, defaultdict

from src.common.cli import build_parser
from src.common.config import CRAWLED_DIR, INPUT_DIR, URLS_DIR, load_settings
from src.common.io_utils import read_csv_dicts, write_csv_dicts
from src.common.logging_setup import get_logger

log = get_logger("expansion.extract_entities", "discovery.log")

DEDUPED_PATH = URLS_DIR / "url_candidates_deduped.csv"
CRAWL_METADATA_PATH = CRAWLED_DIR / "crawl_metadata.csv"

ENTITY_COLUMNS = ["entity", "entity_type", "source_count", "examples"]

_TITLE_SPAN = re.compile(r"\b([A-Z][A-Za-z&'’-]+(?: [A-Z][A-Za-z&'’-]+){1,3})\b")
_COUNTY = re.compile(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)?) County\b")

_COMPANY_HINTS = {
    "Battery", "Motors", "Motor", "Energy", "Automotive", "Manufacturing",
    "Materials", "Solutions", "Systems", "America", "Group", "Industries",
    "Technologies", "Mobility", "Power", "Electric", "Chemical", "Aviation",
}
_COMPANY_SUFFIXES = {"Inc", "LLC", "Corp", "Co", "Ltd", "Company"}
_STOP_ENTITIES = {
    "electric vehicle", "electric vehicles", "united states", "georgia",
    "new georgia", "supply chain", "press release", "economic development",
    "electric vehicle supply", "battery manufacturing", "north america",
}


def extract_companies(text: str) -> set[str]:
    companies = set()
    for span in _TITLE_SPAN.findall(text or ""):
        words = span.split()
        if words[0] == "The":
            words = words[1:]
        if len(words) < 2:
            continue
        span = " ".join(words)
        if span.casefold() in _STOP_ENTITIES:
            continue
        last = words[-1].rstrip(".")
        if last in _COMPANY_SUFFIXES or any(w in _COMPANY_HINTS for w in words):
            companies.add(span)
    return companies


def extract_locations(text: str) -> set[str]:
    return {f"{name} County" for name in _COUNTY.findall(text or "")}


def main() -> None:
    parser = build_parser(__doc__)
    parser.add_argument("--iteration", type=int, default=1, help="expansion iteration (>= 1)")
    args = parser.parse_args()
    settings = load_settings(args.config_dir)

    known = {
        r.get("company", "").casefold() for r in read_csv_dicts(INPUT_DIR / "seed_companies.csv")
    } | {r.get("location", "").casefold() for r in read_csv_dicts(INPUT_DIR / "seed_locations.csv")}

    texts = [
        f"{row.get('title', '')} {row.get('snippet', '')}"
        for row in read_csv_dicts(DEDUPED_PATH)
    ]
    # iteration >= 2 also mines crawled page titles (spec's expansion loop)
    if args.iteration >= 2:
        texts += [row.get("title", "") for row in read_csv_dicts(CRAWL_METADATA_PATH)]

    counts: Counter[tuple[str, str]] = Counter()
    examples: dict[tuple[str, str], str] = defaultdict(str)
    for text in texts:
        for company in extract_companies(text):
            if company.casefold() not in known:
                counts[(company, "company")] += 1
                examples.setdefault((company, "company"), text[:120])
        for location in extract_locations(text):
            if location.casefold() not in known:
                counts[(location, "location")] += 1
                examples.setdefault((location, "location"), text[:120])

    max_entities = int(settings.search.get("max_entities_per_iteration", 30))
    top = counts.most_common(args.limit or max_entities)
    rows = [
        {"entity": entity, "entity_type": etype, "source_count": count, "examples": examples[(entity, etype)]}
        for (entity, etype), count in top
    ]

    out_path = URLS_DIR / f"expansion_entities_iter_{args.iteration}.csv"
    if args.dry_run:
        log.info("[dry-run] would write %d entities to %s", len(rows), out_path)
        return
    write_csv_dicts(out_path, rows, ENTITY_COLUMNS)
    log.info(
        "Extracted %d entities (of %d distinct) from %d texts -> %s",
        len(rows),
        len(counts),
        len(texts),
        out_path,
    )


if __name__ == "__main__":
    main()

"""Stage 6, grouping: cluster validated page records by canonical entity name ->
data/wiki/entity_groups.jsonl.

Deterministic and conservative: casefold + strip punctuation/legal suffixes,
apply the configured alias map (acronyms like HMGMA won't fuzzy-match), then
greedy fuzzy clustering at token_sort_ratio >= 90. Under-merging is safe (the
LLM merge and human review can fix it); over-merging corrupts entities.
Near-misses in [80, 90) are flagged needs_review."""

import hashlib
import re
from collections import defaultdict

from src.common.cli import build_parser
from src.common.config import WIKI_DIR, load_settings
from src.common.io_utils import read_jsonl, write_jsonl
from src.common.logging_setup import get_logger

log = get_logger("wiki_generation.group_records_by_entity", "wiki_generation.log")

RECORDS_VALIDATED_PATH = WIKI_DIR / "wiki_records_validated.jsonl"
GROUPS_PATH = WIKI_DIR / "entity_groups.jsonl"

_LEGAL_SUFFIXES = {"inc", "llc", "corp", "corporation", "co", "ltd", "company"}


def normalize_name(name: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (name or "").casefold())
    words = [w for w in text.split() if w not in _LEGAL_SUFFIXES]
    return " ".join(words)


def _alias_lookup(settings) -> dict[str, str]:
    lookup = {}
    for canonical, aliases in (settings.wiki_schema.get("entity_aliases") or {}).items():
        lookup[normalize_name(canonical)] = canonical
        for alias in aliases or []:
            lookup[normalize_name(alias)] = canonical
    return lookup


def cluster_names(names: list[str], threshold: int, review_threshold: int):
    """Greedy clustering of normalized names. Returns (cluster_of_name, review_pairs)."""
    from rapidfuzz import fuzz

    cluster_of: dict[str, str] = {}
    representatives: list[str] = []
    review_pairs: list[tuple[str, str]] = []
    for name in sorted(names, key=len, reverse=True):
        best_rep, best_score = None, 0
        for rep in representatives:
            score = fuzz.token_sort_ratio(name, rep)
            if score > best_score:
                best_rep, best_score = rep, score
        if best_rep is not None and best_score >= threshold:
            cluster_of[name] = best_rep
            continue
        if best_rep is not None and best_score >= review_threshold:
            review_pairs.append((name, best_rep))
        representatives.append(name)
        cluster_of[name] = name
    return cluster_of, review_pairs


def main() -> None:
    args = build_parser(__doc__).parse_args()
    settings = load_settings(args.config_dir)
    threshold = int(settings.wiki_schema.get("entity_cluster_threshold", 90))
    review_threshold = int(settings.wiki_schema.get("entity_review_threshold", 80))

    records = read_jsonl(RECORDS_VALIDATED_PATH)
    if args.limit:
        records = records[: args.limit]
    aliases = _alias_lookup(settings)

    normalized_of: dict[int, str] = {}
    for i, record in enumerate(records):
        raw_name = record.get("canonical_name") or record.get("entity_name") or ""
        normalized = normalize_name(raw_name)
        normalized = normalize_name(aliases.get(normalized, raw_name))
        normalized_of[i] = normalized

    cluster_of, review_pairs = cluster_names(
        sorted(set(normalized_of.values())), threshold, review_threshold
    )
    review_names = {name for pair in review_pairs for name in pair}

    members: dict[str, list[dict]] = defaultdict(list)
    for i, record in enumerate(records):
        members[cluster_of[normalized_of[i]]].append(record)

    groups = []
    for cluster_key, cluster_records in sorted(members.items()):
        names = [r.get("canonical_name") or r.get("entity_name") or "" for r in cluster_records]
        # most frequent original name wins; ties broken by length (more descriptive)
        canonical = max(set(names), key=lambda n: (names.count(n), len(n)))
        config_canonical = aliases.get(normalize_name(canonical))
        if config_canonical:
            canonical = config_canonical
        groups.append(
            {
                "group_id": hashlib.sha1(cluster_key.encode("utf-8")).hexdigest()[:12],
                "canonical_name": canonical,
                "aliases": sorted({n for n in names if n and n != canonical}),
                "record_count": len(cluster_records),
                "needs_review": cluster_key in review_names,
                "records": cluster_records,
            }
        )

    if args.dry_run:
        log.info("[dry-run] %d records -> %d entity groups", len(records), len(groups))
        return
    write_jsonl(GROUPS_PATH, groups)
    log.info(
        "Grouped %d records into %d entities (%d flagged needs_review) -> %s",
        len(records),
        len(groups),
        sum(1 for g in groups if g["needs_review"]),
        GROUPS_PATH,
    )


if __name__ == "__main__":
    main()

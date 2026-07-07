"""Stage 6, grouping: cluster validated page records by canonical entity name ->
data/wiki/entity_groups.jsonl.

Deterministic and conservative: casefold + strip punctuation/legal suffixes,
apply the configured alias map (acronyms like HMGMA won't fuzzy-match), then
greedy fuzzy clustering at token_sort_ratio >= 90. Under-merging is safe (the
LLM merge and human review can fix it); over-merging corrupts entities.
Near-misses in [80, 90) are flagged needs_review.

Name similarity alone is not a reliable merge signal: a parent company, its own
facility, and an unrelated but similarly-named company can all share most of
their tokens (e.g. "Hyundai Motor Group" vs "Hyundai Motor Group Metaplant
America"). So clustering is entity-type-aware: records are partitioned by
entity_type first and only fuzzy-matched for names within the same type,
never across types. Within a type, if two records' locations are both given
and clearly disagree, a would-be auto-merge is downgraded to needs_review
instead, since same name + same type + different place is exactly the "same
name, different entity" case name-matching alone can't tell apart."""

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


_LOCATION_FILLER_WORDS = {"county", "georgia", "state", "united", "states", "ga", "usa"}


def _normalize_location(loc: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (loc or "").casefold())
    words = [w for w in text.split() if w not in _LOCATION_FILLER_WORDS]
    return " ".join(words)


def _locations_conflict(loc_a: str, loc_b: str) -> bool:
    """True only when both locations are given and clearly don't match — an empty
    location on either side is "unknown", not a conflict. Filler words like
    "County"/"Georgia" are stripped first so "Jackson County" vs "Coweta County"
    doesn't look similar just because they share the word "County"."""
    from rapidfuzz import fuzz

    norm_a, norm_b = _normalize_location(loc_a), _normalize_location(loc_b)
    if not norm_a or not norm_b:
        return False
    return fuzz.token_sort_ratio(norm_a, norm_b) < 60


def cluster_names(
    names: list[str],
    threshold: int,
    review_threshold: int,
    location_of: dict[str, str] | None = None,
):
    """Greedy clustering of normalized names within one entity_type. Returns
    (cluster_of_name, review_pairs). A name-similarity match is downgraded from
    auto-merge to needs_review when both names carry a location and those
    locations clearly disagree (same name/type, different place)."""
    from rapidfuzz import fuzz

    location_of = location_of or {}
    cluster_of: dict[str, str] = {}
    representatives: list[str] = []
    review_pairs: list[tuple[str, str]] = []
    for name in sorted(names, key=len, reverse=True):
        best_rep, best_score = None, 0
        for rep in representatives:
            score = fuzz.token_sort_ratio(name, rep)
            if score > best_score:
                best_rep, best_score = rep, score
        conflict = best_rep is not None and _locations_conflict(
            location_of.get(name, ""), location_of.get(best_rep, "")
        )
        if best_rep is not None and best_score >= threshold and not conflict:
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
    type_of: dict[int, str] = {}
    location_of_record: dict[int, str] = {}
    for i, record in enumerate(records):
        raw_name = record.get("canonical_name") or record.get("entity_name") or ""
        normalized = normalize_name(raw_name)
        normalized = normalize_name(aliases.get(normalized, raw_name))
        normalized_of[i] = normalized
        type_of[i] = record.get("entity_type") or ""
        location_of_record[i] = record.get("county") or record.get("location") or ""

    # Partition by entity_type first: name similarity alone can't tell a company
    # apart from its own facility or an unrelated same-named company, so records
    # of different entity_type are never fuzzy-matched into the same cluster.
    names_by_type: dict[str, set[str]] = defaultdict(set)
    location_by_name_in_type: dict[str, dict[str, str]] = defaultdict(dict)
    for i in range(len(records)):
        t = type_of[i]
        name = normalized_of[i]
        names_by_type[t].add(name)
        loc = location_of_record[i]
        if loc and name not in location_by_name_in_type[t]:
            location_by_name_in_type[t][name] = loc

    cluster_of: dict[tuple[str, str], str] = {}
    review_names: set[tuple[str, str]] = set()
    for entity_type, names in names_by_type.items():
        type_cluster_of, review_pairs = cluster_names(
            sorted(names), threshold, review_threshold, location_by_name_in_type[entity_type]
        )
        for name, rep in type_cluster_of.items():
            cluster_of[(entity_type, name)] = rep
        for name, rep in review_pairs:
            review_names.add((entity_type, name))
            review_names.add((entity_type, rep))

    members: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for i, record in enumerate(records):
        key = (type_of[i], cluster_of[(type_of[i], normalized_of[i])])
        members[key].append(record)

    groups = []
    for (entity_type, cluster_key), cluster_records in sorted(members.items()):
        names = [r.get("canonical_name") or r.get("entity_name") or "" for r in cluster_records]
        # most frequent original name wins; ties broken by length (more descriptive)
        canonical = max(set(names), key=lambda n: (names.count(n), len(n)))
        config_canonical = aliases.get(normalize_name(canonical))
        if config_canonical:
            canonical = config_canonical
        group_id_source = f"{entity_type}:{cluster_key}"
        groups.append(
            {
                "group_id": hashlib.sha1(group_id_source.encode("utf-8")).hexdigest()[:12],
                "canonical_name": canonical,
                "aliases": sorted({n for n in names if n and n != canonical}),
                "record_count": len(cluster_records),
                "needs_review": (entity_type, cluster_key) in review_names,
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

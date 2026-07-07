#!/usr/bin/env python3
"""Build a browsable LLM Wiki (Obsidian-style markdown vault) from validated records.

This is the "ingest" operation of the LLM Wiki pattern (see wiki/README.md),
run in batch over the whole validated corpus instead of one source at a time.
It reads the source-grounded records produced by the wiki-generation pipeline
(``data/wiki/wiki_records_validated.jsonl``) and compiles them into an
interlinked set of markdown pages under ``wiki/``:

    wiki/entities/<slug>.md    one page per canonical entity (companies, JVs, ...)
    wiki/concepts/<slug>.md    one page per supply-chain category
    wiki/geography/<slug>.md   one page per Georgia county
    wiki/index.md              catalog of every page
    wiki/log.md                append-only chronological build log

The narrative pages (README.md, CLAUDE.md, overview.md, synthesis.md) are
hand-maintained and are NOT overwritten by this script.

Every fact keeps its ``source_url`` + ``evidence_text``, so the wiki stays
source-backed. The script is idempotent: rerunning it regenerates the
generated pages deterministically and never duplicates.

Usage:
    python scripts/build_llm_wiki.py
    python scripts/build_llm_wiki.py --records data/wiki/wiki_records_validated.jsonl --out wiki
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Human-readable labels for the supply_chain_category slugs used in the records.
CATEGORY_LABELS = {
    "battery_materials": "Battery Materials",
    "battery_cell_manufacturing": "Battery Cell Manufacturing",
    "battery_recycling": "Battery Recycling",
    "vehicle_manufacturing": "Vehicle Manufacturing",
    "automotive_components": "Automotive Components",
    "power_electronics": "Power Electronics",
    "thermal_management": "Thermal Management",
    "charging_infrastructure": "Charging Infrastructure",
    "government_support": "Government Support",
    "workforce_training": "Workforce Training",
    "research_and_development": "Research & Development",
    "logistics": "Logistics",
    "unknown": "Uncategorized",
}

ENTITY_TYPE_LABELS = {
    "company": "Company",
    "facility": "Facility",
    "joint_venture": "Joint Venture",
    "government_program": "Government Program",
    "workforce_training": "Workforce Training",
    "person": "Person",
    "research_center": "Research Center",
    "policy_or_incentive": "Policy / Incentive",
    "event": "Event",
    "charging_infrastructure": "Charging Infrastructure",
    "investment_announcement": "Investment Announcement",
}


def slugify(name: str) -> str:
    """Turn an entity/category name into a stable, filesystem-safe slug."""
    s = name.strip().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[‐-―‘’“”]", "", s)  # dashes/quotes
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "unnamed"


_LEGAL_SUFFIX = re.compile(
    r"[\s,]+(inc|incorporated|llc|l\.l\.c|corp|corporation|co|ltd|plc|lp|llp|gmbh|"
    r"holdings?|group|america)\.?$",
    re.IGNORECASE,
)


def canonical_key(name: str) -> str:
    """Collapse surface variants of an entity name into one merge key.

    Strips trailing legal suffixes (Inc., LLC, Corp., ...) repeatedly and
    normalizes punctuation, so 'SK Battery America, Inc.' and 'SK Battery
    America' resolve to the same key. Purely for merging — display names are
    chosen separately.
    """
    s = norm(name).lower()
    s = re.sub(r"[.,]", "", s)
    prev = None
    while prev != s:
        prev = s
        s = _LEGAL_SUFFIX.sub("", s).strip()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s or norm(name).lower()


def normalize_county(county: str) -> str:
    """Normalize 'Bryan' and 'Bryan County' to a single 'Bryan County' form."""
    c = norm(county)
    if not c:
        return ""
    c = re.sub(r"\s+county\s*$", "", c, flags=re.IGNORECASE).strip()
    if not c:
        return ""
    return f"{c} County"


def norm(text: str | None) -> str:
    """Normalize unicode-ish whitespace/dashes from the LLM output for clean markdown."""
    if not text:
        return ""
    return (
        text.replace("‑", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace(" ", " ")
        .replace(" ", " ")
        .strip()
    )


def load_records(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def merge_entities(records: list[dict]) -> dict[str, dict]:
    """Merge the many source-level records into one aggregate per canonical entity."""
    entities: dict[str, dict] = {}
    for r in records:
        name = norm(r.get("canonical_name") or r.get("entity_name"))
        if not name:
            continue
        key = canonical_key(name)
        e = entities.get(key)
        if e is None:
            e = {
                "slug": key,  # provisional; finalized after display name is chosen
                "name": name,
                "_names": defaultdict(int),
                "entity_type": r.get("entity_type", ""),
                "supply_chain_category": r.get("supply_chain_category", "") or "unknown",
                "overview": "",
                "ev_relevance": "",
                "location": "",
                "county": "",
                "state": "",
                "country": "",
                "facilities": [],
                "investment": [],
                "jobs": [],
                "timeline": [],
                "key_facts": [],
                "related_organizations": [],
                "workforce_programs": [],
                "sources": {},  # url -> title
                "_best_conf": -1.0,
            }
            entities[key] = e

        e["_names"][name] += 1
        conf = float(r.get("confidence_score") or 0)
        # Prefer the highest-confidence record for scalar fields.
        if conf > e["_best_conf"]:
            e["_best_conf"] = conf
            for scalar in ("overview", "ev_relevance", "location", "state", "country"):
                val = norm(r.get(scalar))
                if val:
                    e[scalar] = val
            county = normalize_county(r.get("county"))
            if county:
                e["county"] = county
            if r.get("entity_type"):
                e["entity_type"] = r["entity_type"]
            if r.get("supply_chain_category"):
                e["supply_chain_category"] = r["supply_chain_category"]
        else:
            # Backfill any scalar the best record left empty.
            for scalar in ("overview", "ev_relevance", "location", "state", "country"):
                if not e[scalar]:
                    val = norm(r.get(scalar))
                    if val:
                        e[scalar] = val
            if not e["county"]:
                e["county"] = normalize_county(r.get("county"))

        for listy in ("facilities", "investment", "jobs", "timeline", "related_organizations", "workforce_programs"):
            merge_list(e[listy], listy, r.get(listy) or [])
        for fact in r.get("key_facts") or []:
            fact = norm(fact)
            if fact and fact not in e["key_facts"]:
                e["key_facts"].append(fact)

        url = r.get("source_url")
        if url:
            e["sources"].setdefault(url, norm(r.get("source_title")) or url)

    # Choose a display name per entity: the most frequent surface form,
    # tie-broken toward the shorter (usually cleaner) variant. Then set the slug.
    seen_slugs: dict[str, int] = {}
    for e in entities.values():
        best = max(e["_names"].items(), key=lambda kv: (kv[1], -len(kv[0])))[0]
        e["name"] = best
        slug = slugify(best)
        if slug in seen_slugs:  # guard against a rare display-name slug collision
            seen_slugs[slug] += 1
            slug = f"{slug}-{seen_slugs[slug]}"
        else:
            seen_slugs[slug] = 1
        e["slug"] = slug
        del e["_names"]
    return entities


def _dedup_key(listy: str, item: dict) -> str:
    """A normalized identity for a list item so near-duplicate rows collapse."""
    def n(*keys: str) -> str:
        parts = [norm(item.get(k)) for k in keys]
        return re.sub(r"[^a-z0-9]+", "", " ".join(parts).lower())

    if listy == "facilities":
        return n("name", "location", "county")
    if listy == "investment":
        return n("amount", "date")
    if listy == "jobs":
        return n("hiring_goal", "count", "timeline")
    if listy == "timeline":
        return n("date", "event")
    if listy in ("related_organizations", "workforce_programs"):
        return n("name")
    return n("name")


def _richness(item: dict) -> int:
    """How much detail an item carries — used to keep the fullest of duplicates."""
    return sum(len(norm(v)) for v in item.values() if isinstance(v, str))


def merge_list(existing: list[dict], listy: str, new_items: list[dict]) -> None:
    """Merge new_items into existing in place, collapsing near-duplicates by key."""
    index = {_dedup_key(listy, it): i for i, it in enumerate(existing)}
    for item in new_items:
        if not isinstance(item, dict):
            continue
        k = _dedup_key(listy, item)
        if not k:
            continue
        if k in index:
            # Keep whichever row carries more detail.
            i = index[k]
            if _richness(item) > _richness(existing[i]):
                existing[i] = item
        else:
            index[k] = len(existing)
            existing.append(item)


def linkify(name: str, name_to_slug: dict[str, str]) -> str:
    """Wikilink a name if it matches a known entity, else return it plain."""
    slug = name_to_slug.get(canonical_key(name))
    if slug:
        return f"[[{slug}|{name}]]"
    return name


# --------------------------------------------------------------------------- #
# Page rendering
# --------------------------------------------------------------------------- #
def render_entity_page(e: dict, name_to_slug: dict[str, str]) -> str:
    cat = e["supply_chain_category"] or "unknown"
    cat_label = CATEGORY_LABELS.get(cat, cat.replace("_", " ").title())
    type_label = ENTITY_TYPE_LABELS.get(e["entity_type"], e["entity_type"].replace("_", " ").title())

    loc_bits = [b for b in (e["location"], e["county"], e["state"], e["country"]) if b]
    # De-dup while preserving order.
    seen, loc_parts = set(), []
    for b in loc_bits:
        if b.lower() not in seen:
            seen.add(b.lower())
            loc_parts.append(b)
    location = ", ".join(loc_parts)

    tags = [f"type/{e['entity_type']}", f"category/{cat}"]
    if e["county"]:
        tags.append(f"county/{slugify(e['county'])}")

    lines: list[str] = []
    # YAML frontmatter (Dataview-friendly).
    lines.append("---")
    lines.append(f'title: "{e["name"]}"')
    lines.append(f"entity_type: {e['entity_type']}")
    lines.append(f"supply_chain_category: {cat}")
    if e["county"]:
        lines.append(f'county: "{e["county"]}"')
    lines.append(f"facilities: {len(e['facilities'])}")
    lines.append(f"sources: {len(e['sources'])}")
    lines.append(f"tags: [{', '.join(tags)}]")
    lines.append("---")
    lines.append("")
    lines.append(f"# {e['name']}")
    lines.append("")

    meta = [f"**Type:** {type_label}", f"**Supply-chain role:** [[{slugify(cat)}|{cat_label}]]"]
    if location:
        meta.append(f"**Location:** {location}")
    lines.append("  ·  ".join(meta))
    lines.append("")

    if e["overview"]:
        lines.append("## Overview")
        lines.append("")
        lines.append(e["overview"])
        lines.append("")

    if e["ev_relevance"]:
        lines.append("## EV supply-chain relevance")
        lines.append("")
        lines.append(e["ev_relevance"])
        lines.append("")

    if e["facilities"]:
        lines.append("## Facilities")
        lines.append("")
        lines.append("| Facility | Location | County | Status | Capacity |")
        lines.append("| --- | --- | --- | --- | --- |")
        for f in e["facilities"]:
            row = [
                norm(f.get("name")) or "—",
                norm(f.get("location")) or "—",
                norm(f.get("county")) or "—",
                norm(f.get("status")) or "—",
                norm(f.get("capacity")) or "—",
            ]
            lines.append("| " + " | ".join(c.replace("|", "\\|") for c in row) + " |")
        lines.append("")
        details = [f for f in e["facilities"] if norm(f.get("details"))]
        for f in details:
            lines.append(f"- **{norm(f.get('name')) or 'Facility'}** — {norm(f.get('details'))}")
        if details:
            lines.append("")

    if e["investment"]:
        lines.append("## Investment")
        lines.append("")
        for inv in e["investment"]:
            amount = norm(inv.get("amount")) or "Undisclosed"
            when = norm(inv.get("date"))
            head = f"- **{amount}**" + (f" ({when})" if when else "")
            purpose = norm(inv.get("purpose"))
            if purpose:
                head += f" — {purpose}"
            lines.append(head)
            det = norm(inv.get("details"))
            if det:
                lines.append(f"  - {det}")
        lines.append("")

    if e["jobs"]:
        lines.append("## Jobs")
        lines.append("")
        for j in e["jobs"]:
            goal = norm(j.get("hiring_goal")) or norm(j.get("count")) or "Jobs announced"
            timeline = norm(j.get("timeline"))
            line = f"- **{goal}**" + (f" — {timeline}" if timeline else "")
            lines.append(line)
            areas = j.get("hiring_areas") or []
            if areas:
                lines.append(f"  - Areas: {', '.join(norm(a) for a in areas if norm(a))}")
            det = norm(j.get("details"))
            if det:
                lines.append(f"  - {det}")
        lines.append("")

    if e["timeline"]:
        lines.append("## Timeline")
        lines.append("")
        for t in e["timeline"]:
            when = norm(t.get("date")) or "—"
            event = norm(t.get("event"))
            lines.append(f"- **{when}** — {event}")
        lines.append("")

    if e["related_organizations"]:
        lines.append("## Related organizations & people")
        lines.append("")
        for o in e["related_organizations"]:
            oname = norm(o.get("name"))
            if not oname:
                continue
            role = norm(o.get("role"))
            det = norm(o.get("details"))
            line = f"- {linkify(oname, name_to_slug)}"
            if role:
                line += f" — {role}"
            if det:
                line += f". {det}"
            lines.append(line)
        lines.append("")

    if e["workforce_programs"]:
        lines.append("## Workforce & partners")
        lines.append("")
        for w in e["workforce_programs"]:
            wname = norm(w.get("name"))
            if not wname:
                continue
            rel = norm(w.get("relationship"))
            det = norm(w.get("details"))
            line = f"- {linkify(wname, name_to_slug)}"
            if rel:
                line += f" — {rel}"
            if det:
                line += f". {det}"
            lines.append(line)
        lines.append("")

    if e["key_facts"]:
        lines.append("## Key facts")
        lines.append("")
        for fact in e["key_facts"]:
            lines.append(f"- {fact}")
        lines.append("")

    lines.append("## Sources")
    lines.append("")
    for url, title in sorted(e["sources"].items(), key=lambda kv: kv[1].lower()):
        lines.append(f"- [{title}]({url})")
    lines.append("")

    lines.append("---")
    lines.append(f"*See also: [[{slugify(cat)}|{cat_label}]]"
                 + (f", [[county-{slugify(e['county'])}|{e['county']}]]" if e["county"] else "")
                 + ", [[index|Wiki index]]*")
    lines.append("")
    return "\n".join(lines)


def render_concept_page(cat: str, ents: list[dict]) -> str:
    label = CATEGORY_LABELS.get(cat, cat.replace("_", " ").title())
    n_fac = sum(len(e["facilities"]) for e in ents)
    lines = [
        "---",
        f'title: "{label}"',
        "page_type: concept",
        f"supply_chain_category: {cat}",
        f"entities: {len(ents)}",
        f"tags: [concept, category/{cat}]",
        "---",
        "",
        f"# {label}",
        "",
        f"Supply-chain segment covering **{len(ents)} entities** and "
        f"**{n_fac} facilities** in the Georgia EV corpus.",
        "",
        "## Entities",
        "",
    ]
    for e in sorted(ents, key=lambda x: x["name"].lower()):
        summary = (e["ev_relevance"] or e["overview"] or "").split(". ")[0]
        summary = summary[:160] + ("…" if len(summary) > 160 else "")
        loc = e["county"] or e["location"] or e["state"]
        loc = f" _({loc})_" if loc else ""
        lines.append(f"- [[{e['slug']}|{e['name']}]]{loc} — {summary}")
    lines.append("")
    lines.append("---")
    lines.append("*See also: [[index|Wiki index]], [[overview|Corpus overview]]*")
    lines.append("")
    return "\n".join(lines)


def render_county_page(county: str, ents: list[dict]) -> str:
    slug = f"county-{slugify(county)}"
    lines = [
        "---",
        f'title: "{county}"',
        "page_type: geography",
        f'county: "{county}"',
        f"entities: {len(ents)}",
        f"tags: [geography, county/{slugify(county)}]",
        "---",
        "",
        f"# {county}",
        "",
        f"Georgia county with **{len(ents)} EV supply-chain entities** in the corpus.",
        "",
        "## Entities located here",
        "",
    ]
    for e in sorted(ents, key=lambda x: x["name"].lower()):
        cat = CATEGORY_LABELS.get(e["supply_chain_category"], e["supply_chain_category"])
        lines.append(f"- [[{e['slug']}|{e['name']}]] — {cat}")
    lines.append("")
    lines.append("---")
    lines.append("*See also: [[index|Wiki index]], [[overview|Corpus overview]]*")
    lines.append("")
    return "\n".join(lines), slug


def render_index(entities: dict, by_cat: dict, by_county: dict) -> str:
    total_fac = sum(len(e["facilities"]) for e in entities.values())
    total_src = len({u for e in entities.values() for u in e["sources"]})
    lines = [
        "---",
        "title: Index",
        "page_type: index",
        "---",
        "",
        "# Wiki Index",
        "",
        f"*Auto-generated catalog. {len(entities)} entities · {total_fac} facilities · "
        f"{total_src} unique sources.*",
        "",
        "Start here: [[overview|Corpus overview]] · [[synthesis|Evolving synthesis]] · "
        "[[log|Build log]] · [[README|What this wiki is]] · [[CLAUDE|Schema & conventions]]",
        "",
        "## Concepts — supply-chain segments",
        "",
    ]
    for cat, ents in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        label = CATEGORY_LABELS.get(cat, cat.replace("_", " ").title())
        lines.append(f"- [[{slugify(cat)}|{label}]] — {len(ents)} entities")
    lines.append("")
    lines.append("## Geography — counties")
    lines.append("")
    for county, ents in sorted(by_county.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"- [[county-{slugify(county)}|{county}]] — {len(ents)} entities")
    lines.append("")
    lines.append("## Entities (A–Z)")
    lines.append("")
    for e in sorted(entities.values(), key=lambda x: x["name"].lower()):
        cat = CATEGORY_LABELS.get(e["supply_chain_category"], e["supply_chain_category"])
        lines.append(f"- [[{e['slug']}|{e['name']}]] — {cat}")
    lines.append("")
    return "\n".join(lines)


def append_log(log_path: Path, entities: dict, by_cat: dict, by_county: dict) -> None:
    total_fac = sum(len(e["facilities"]) for e in entities.values())
    total_src = len({u for e in entities.values() for u in e["sources"]})
    entry = (
        f"## [{date.today().isoformat()}] build | full corpus regenerate\n"
        f"- Generated {len(entities)} entity pages, {len(by_cat)} concept pages, "
        f"{len(by_county)} county pages from `data/wiki/wiki_records_validated.jsonl`.\n"
        f"- Coverage: {total_fac} facilities, {total_src} unique sources.\n\n"
    )
    header = ""
    if not log_path.exists():
        header = ("# Build Log\n\nAppend-only chronological record of wiki operations "
                  "(ingest / build / query / lint).\n\n")
    with log_path.open("a", encoding="utf-8") as f:
        if header:
            f.write(header)
        f.write(entry)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the LLM Wiki markdown vault.")
    ap.add_argument("--records", default=str(REPO_ROOT / "data/wiki/wiki_records_validated.jsonl"))
    ap.add_argument("--out", default=str(REPO_ROOT / "wiki"))
    args = ap.parse_args()

    records_path = Path(args.records)
    out = Path(args.out)
    records = load_records(records_path)
    entities = merge_entities(records)

    name_to_slug = {}
    for e in entities.values():
        name_to_slug[canonical_key(e["name"])] = e["slug"]

    by_cat: dict[str, list] = defaultdict(list)
    by_county: dict[str, list] = defaultdict(list)
    for e in entities.values():
        by_cat[e["supply_chain_category"] or "unknown"].append(e)
        if e["county"]:
            by_county[e["county"]].append(e)

    # Wipe & rewrite only the generated subtrees; leave narrative pages intact.
    for sub in ("entities", "concepts", "geography"):
        d = out / sub
        if d.exists():
            for p in d.glob("*.md"):
                p.unlink()
        d.mkdir(parents=True, exist_ok=True)

    for e in entities.values():
        (out / "entities" / f"{e['slug']}.md").write_text(
            render_entity_page(e, name_to_slug), encoding="utf-8"
        )
    for cat, ents in by_cat.items():
        (out / "concepts" / f"{slugify(cat)}.md").write_text(
            render_concept_page(cat, ents), encoding="utf-8"
        )
    for county, ents in by_county.items():
        page, slug = render_county_page(county, ents)
        (out / "geography" / f"{slug}.md").write_text(page, encoding="utf-8")

    (out / "index.md").write_text(render_index(entities, by_cat, by_county), encoding="utf-8")
    append_log(out / "log.md", entities, by_cat, by_county)

    print(f"Wrote {len(entities)} entity pages, {len(by_cat)} concept pages, "
          f"{len(by_county)} county pages to {out}/")


if __name__ == "__main__":
    main()

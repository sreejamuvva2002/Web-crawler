"""Record-level validation checks (spec Stage 6), labeled with the spec's
rejection reasons. Importable functions; as a CLI it validates entity-level
profiles (wiki_entities_raw.jsonl -> wiki_entities_validated.jsonl)."""

import datetime as dt

from src.common.cli import build_parser
from src.common.config import WIKI_DIR, load_settings
from src.common.io_utils import read_jsonl, write_jsonl
from src.common.logging_setup import get_logger

log = get_logger("validation.validate_wiki_records", "validation.log")

ENTITIES_RAW_PATH = WIKI_DIR / "wiki_entities_raw.jsonl"
ENTITIES_VALIDATED_PATH = WIKI_DIR / "wiki_entities_validated.jsonl"
ENTITIES_FAILED_PATH = WIKI_DIR / "wiki_entities_failed.jsonl"

# Advancement order for aggregating an entity's status from its per-page sources.
# Higher = further along. cancelled/superseded are terminal overrides set only by
# a later cross-source reconciliation step, never emitted per page.
_CLAIM_STATUS_RANK = {
    "announced": 1,
    "under_construction": 2,
    "operational": 3,
    "superseded": 4,
    "cancelled": 5,
}


# Navigational chrome / non-entities that leak into related_organizations:
# related-link blocks, press & communications staff (contacts, not project
# partners), and bare geographic locations (a city/state is not an organization).
_RELATED_LINK_MARKERS = (
    "related link",
    "related article",
    "more news",
    "read more",
    "see also",
    "press contact",
    "media contact",
    "press secretary",
    "communications manager",
    "communications director",
    "media relations",
    "spokesperson",
    "public relations",
    "press office",
    "navigation",
    "sidebar",
    # bare-location entries (role like "Location of existing footprint")
    "location of",
    "footprint",
)

# The outlet that published, syndicated, or distributed the article is source
# metadata, not a related organization (e.g. "Atlanta Journal-Constitution" /
# "Tribune Content Agency"). Matched against name+role+details so both the
# byline org and its distributor role are caught.
_PUBLISHER_MARKERS = (
    "publication of the article",
    "publisher of the article",
    "distributor of the article",
    "distributed by",
    "syndicat",  # syndicated / syndication
    "content agency",
    "wire service",
    "news agency",
    "republished",
    "reprinted",
)


def _parse_date(value: str):
    """Lenient ISO-ish date parse: accepts YYYY-MM-DD[THH:..], YYYY-MM, YYYY."""
    value = (value or "").strip()
    if not value:
        return None
    for text, fmt in ((value[:10], "%Y-%m-%d"), (value[:7], "%Y-%m"), (value[:4], "%Y")):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def compute_currency(publication_date: str, as_of: str, settings) -> str:
    """Deterministic freshness bucket from age(publication_date -> as_of).

    Purely date arithmetic — the LLM never scores this. No/unparseable
    publication_date yields ``undated`` (never a validation failure)."""
    st = (settings.wiki_schema.get("staleness") or {}) if settings else {}
    fresh_max = float(st.get("fresh_max_months", 12))
    stale_min = float(st.get("stale_min_months", 24))
    pub = _parse_date(publication_date)
    if pub is None:
        return "undated"
    ref = _parse_date(as_of) or dt.date.today()
    age_months = (ref.year - pub.year) * 12 + (ref.month - pub.month)
    if ref.day < pub.day:
        age_months -= 1
    age_months = max(age_months, 0)
    if age_months < fresh_max:
        return "fresh"
    if age_months < stale_min:
        return "aging"
    return "stale"


def stamp_currency(record: dict, settings, as_of: str | None = None) -> str:
    """Stamp as_of + deterministic currency onto a page-level record in place."""
    as_of = (
        as_of
        or (record.get("as_of") or "").strip()
        or (record.get("generation_date") or "").strip()
        or dt.date.today().isoformat()
    )
    record["as_of"] = as_of
    record["currency"] = compute_currency(record.get("publication_date", ""), as_of, settings)
    return record["currency"]


def stamp_entity_currency(profile: dict, settings, as_of: str | None = None) -> str:
    """Stamp as_of, publication_date_range, and currency onto an entity profile.

    Entity currency reflects the *freshest* source (how recent our newest info
    about the entity is); individual timeline facts keep their own dates."""
    as_of = (
        as_of
        or (profile.get("as_of") or "").strip()
        or (profile.get("generation_date") or "").strip()
        or dt.date.today().isoformat()
    )
    profile["as_of"] = as_of
    sources = profile.get("sources") or []
    # Aggregate claim_status deterministically: the most-advanced across sources.
    ranked = [
        ((s or {}).get("claim_status") or "").strip()
        for s in sources
        if ((s or {}).get("claim_status") or "").strip() in _CLAIM_STATUS_RANK
    ]
    if ranked and not (profile.get("claim_status") or "").strip():
        profile["claim_status"] = max(ranked, key=lambda s: _CLAIM_STATUS_RANK[s])
    dates = [d for d in (_parse_date((s or {}).get("publication_date")) for s in sources) if d]
    if not dates:
        profile.setdefault("publication_date_range", "")
        profile["currency"] = "undated"
        return "undated"
    earliest, latest = min(dates), max(dates)
    profile["publication_date_range"] = (
        earliest.isoformat() if earliest == latest else f"{earliest.isoformat()} .. {latest.isoformat()}"
    )
    profile["currency"] = compute_currency(latest.isoformat(), as_of, settings)
    return profile["currency"]


def _normalize_county(value: str) -> str:
    """Ensure a Georgia county reads as 'X County' (e.g. 'Jackson' -> 'Jackson County').

    Leaves blanks, values already ending in 'County', and parenthetical/independent
    forms untouched."""
    value = (value or "").strip()
    if not value or value.casefold().endswith("county"):
        return value
    return f"{value} County"


def _cap_confidence(value, ceiling: float) -> float:
    try:
        return min(float(value or 0.0), ceiling)
    except (TypeError, ValueError):
        return 0.0


def _references_georgia(text: str) -> bool:
    text = (text or "").casefold()
    return "georgia" in text or text.strip().endswith(", ga")


def _relocate_to_georgia_project(record: dict) -> None:
    """Safety net for the HQ-overrides-project-location bug: when the top-level
    location is the company's out-of-state HQ but the page is about a Georgia
    facility, adopt the Georgia facility's location/county for the top-level and
    preserve the HQ in `headquarters`. Only fires when it is unambiguous."""
    if (record.get("state") or "").strip().casefold() != "georgia":
        return
    ga_facility = next(
        (f for f in (record.get("facilities") or [])
         if isinstance(f, dict) and _references_georgia(f.get("location") or f.get("county") or "")),
        None,
    )
    # county: adopt the Georgia facility's county when the top-level one is blank
    if not (record.get("county") or "").strip() and ga_facility and (ga_facility.get("county") or "").strip():
        record["county"] = ga_facility["county"]
    # location: if the top-level location is clearly not the Georgia project
    # (an out-of-state HQ) and we have a Georgia facility, swap them
    location = (record.get("location") or "").strip()
    if ga_facility and location and not _references_georgia(location):
        if not (record.get("headquarters") or "").strip():
            record["headquarters"] = location
        if (ga_facility.get("location") or "").strip():
            record["location"] = ga_facility["location"]


def normalize_record(record: dict, settings) -> dict:
    """Deterministic cleanup applied to every page record, in place: county-name
    suffixing (top-level + per-facility), the Georgia-project location safety net,
    and a pre-validation confidence ceiling (1.0 is reserved for records that have
    cleared validation)."""
    ceiling = float((settings.wiki_schema.get("max_pre_validation_confidence", 0.95)) if settings else 0.95)
    for facility in record.get("facilities") or []:
        if isinstance(facility, dict):
            facility["county"] = _normalize_county(facility.get("county", ""))
    _relocate_to_georgia_project(record)
    record["county"] = _normalize_county(record.get("county", ""))
    record["confidence_score"] = _cap_confidence(record.get("confidence_score"), ceiling)
    return record


def normalize_entity(profile: dict, settings) -> dict:
    """normalize_record's entity-level analog: per-facility county suffixing and
    the same pre-validation confidence ceiling."""
    ceiling = float((settings.wiki_schema.get("max_pre_validation_confidence", 0.95)) if settings else 0.95)
    for facility in profile.get("facilities") or []:
        if isinstance(facility, dict):
            facility["county"] = _normalize_county(facility.get("county", ""))
    profile["confidence_score"] = _cap_confidence(profile.get("confidence_score"), ceiling)
    return profile


def clean_related_organizations(record: dict) -> int:
    """Drop navigational-chrome entries from related_organizations, in place.

    Removes any entry explicitly marked ``source: related_link`` or whose
    role/details match a known related-link/press-contact pattern. Returns the
    number dropped so callers can log retro-cleaning of old records."""
    orgs = record.get("related_organizations") or []
    kept, removed = [], 0
    for org in orgs:
        org = org or {}
        if (org.get("source") or "body").strip().casefold() == "related_link":
            removed += 1
            continue
        blob = " ".join(str(org.get(f, "")) for f in ("role", "details")).casefold()
        if any(marker in blob for marker in _RELATED_LINK_MARKERS):
            removed += 1
            continue
        blob_all = " ".join(str(org.get(f, "")) for f in ("name", "role", "details")).casefold()
        if any(marker in blob_all for marker in _PUBLISHER_MARKERS):
            removed += 1
            continue
        kept.append(org)
    record["related_organizations"] = kept
    return removed


def _georgia_related(record: dict) -> bool:
    if (record.get("state") or "").strip().casefold() == "georgia":
        return True
    haystack = " ".join(
        str(record.get(field, ""))
        for field in ("location", "county", "overview", "ev_relevance", "evidence_text")
    ).casefold()
    return "georgia" in haystack


def validate_page_record(record: dict, settings) -> list[str]:
    """Return the spec rejection reasons this record trips (empty = valid)."""
    schema = settings.wiki_schema
    reasons = []
    if not (record.get("source_url") or "").strip():
        reasons.append("missing_source_url")
    if not (record.get("evidence_text") or "").strip():
        reasons.append("missing_evidence")
    if not (record.get("entity_name") or "").strip() or not (record.get("overview") or "").strip():
        reasons.append("too_generic")
    if not _georgia_related(record):
        reasons.append("not_georgia_related")
    if not (record.get("ev_relevance") or "").strip():
        reasons.append("not_ev_related")
    if record.get("entity_type") not in schema.get("entity_types", []):
        reasons.append("invalid_entity_type")
    if record.get("supply_chain_category") not in schema.get("supply_chain_categories", []):
        reasons.append("invalid_supply_chain_category")
    claim_status = (record.get("claim_status") or "").strip()
    if claim_status and claim_status not in schema.get("claim_statuses", []):
        reasons.append("invalid_claim_status")
    if float(record.get("confidence_score") or 0) < float(schema.get("min_confidence_score", 0.3)):
        reasons.append("low_confidence")
    return reasons


def validate_entity_profile(profile: dict, settings) -> list[str]:
    schema = settings.wiki_schema
    reasons = []
    if not (profile.get("canonical_name") or "").strip():
        reasons.append("too_generic")
    sources = profile.get("sources") or []
    if not sources or not any((s.get("source_url") or "").strip() for s in sources):
        reasons.append("missing_source_url")
    if not any((s.get("evidence_text") or "").strip() for s in sources):
        reasons.append("missing_evidence")
    if profile.get("entity_type") not in schema.get("entity_types", []):
        reasons.append("invalid_entity_type")
    claim_status = (profile.get("claim_status") or "").strip()
    if claim_status and claim_status not in schema.get("claim_statuses", []):
        reasons.append("invalid_claim_status")
    if float(profile.get("confidence_score") or 0) < float(schema.get("min_confidence_score", 0.3)):
        reasons.append("low_confidence")
    return reasons


def main() -> None:
    args = build_parser(__doc__).parse_args()
    settings = load_settings(args.config_dir)

    profiles = read_jsonl(ENTITIES_RAW_PATH)
    if args.limit:
        profiles = profiles[: args.limit]
    passed, failed = [], []
    dropped_links = 0
    for profile in profiles:
        dropped_links += clean_related_organizations(profile)
        normalize_entity(profile, settings)
        stamp_entity_currency(profile, settings)
        reasons = validate_entity_profile(profile, settings)
        if reasons:
            profile["validation_status"] = "failed"
            profile["rejection_reasons"] = reasons
            failed.append(profile)
        else:
            profile["validation_status"] = "passed"
            passed.append(profile)

    if args.dry_run:
        log.info("[dry-run] %d entities would pass, %d fail", len(passed), len(failed))
        return
    write_jsonl(ENTITIES_VALIDATED_PATH, passed)
    write_jsonl(ENTITIES_FAILED_PATH, failed)
    log.info(
        "Entities: %d passed -> %s, %d failed -> %s (dropped %d related-link chrome entries)",
        len(passed),
        ENTITIES_VALIDATED_PATH,
        len(failed),
        ENTITIES_FAILED_PATH,
        dropped_links,
    )


if __name__ == "__main__":
    main()

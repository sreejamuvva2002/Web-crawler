"""Record-level validation checks (spec Stage 6), labeled with the spec's
rejection reasons. Importable functions; as a CLI it validates entity-level
profiles (wiki_entities_raw.jsonl -> wiki_entities_validated.jsonl)."""

from src.common.cli import build_parser
from src.common.config import WIKI_DIR, load_settings
from src.common.io_utils import read_jsonl, write_jsonl
from src.common.logging_setup import get_logger

log = get_logger("validation.validate_wiki_records", "validation.log")

ENTITIES_RAW_PATH = WIKI_DIR / "wiki_entities_raw.jsonl"
ENTITIES_VALIDATED_PATH = WIKI_DIR / "wiki_entities_validated.jsonl"
ENTITIES_FAILED_PATH = WIKI_DIR / "wiki_entities_failed.jsonl"


def _georgia_related(record: dict) -> bool:
    if (record.get("state") or "").strip().casefold() == "georgia":
        return True
    haystack = " ".join(
        str(record.get(field, ""))
        for field in ("location", "county", "summary", "ev_relevance", "evidence_text")
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
    if not (record.get("entity_name") or "").strip() or not (record.get("summary") or "").strip():
        reasons.append("too_generic")
    if not _georgia_related(record):
        reasons.append("not_georgia_related")
    if not (record.get("ev_relevance") or "").strip():
        reasons.append("not_ev_related")
    if record.get("entity_type") not in schema.get("entity_types", []):
        reasons.append("invalid_entity_type")
    if record.get("supply_chain_category") not in schema.get("supply_chain_categories", []):
        reasons.append("invalid_supply_chain_category")
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
    for profile in profiles:
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
        "Entities: %d passed -> %s, %d failed -> %s",
        len(passed),
        ENTITIES_VALIDATED_PATH,
        len(failed),
        ENTITIES_FAILED_PATH,
    )


if __name__ == "__main__":
    main()

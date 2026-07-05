"""Stage 6, pass 2: one Qwen merge call per entity group -> entity-level wiki
profiles in data/wiki/wiki_entities_raw.jsonl.

Resume: groups whose group_id already appears in the raw file are skipped.
Source preservation is enforced after the call — any input source_url the model
dropped is restored from the group's records (spec merge rule 2/6)."""

import datetime as dt
import sys

from src.common.cli import build_parser
from src.common.config import WIKI_DIR, ensure_data_dirs, load_settings
from src.common.io_utils import append_jsonl, iter_jsonl, read_jsonl
from src.common.logging_setup import get_logger
from src.validation.wiki_schema import EntitySource, EntityWikiProfile
from src.wiki_generation.llm_client import LLMError, get_llm_client
from src.wiki_generation.qwen_entity_merge_prompt import build_merge_prompt

log = get_logger("wiki_generation.generate_entity_wiki", "wiki_generation.log")

GROUPS_PATH = WIKI_DIR / "entity_groups.jsonl"
ENTITIES_RAW_PATH = WIKI_DIR / "wiki_entities_raw.jsonl"
ENTITIES_FAILED_PATH = WIKI_DIR / "wiki_entities_failed.jsonl"

_STAMP_FIELDS = ("wiki_id", "page_id", "generated_by_model", "generation_date", "validation_status")


def _restore_dropped_sources(profile: EntityWikiProfile, records: list[dict]) -> int:
    present = {s.source_url for s in profile.sources}
    restored = 0
    for record in records:
        url = record.get("source_url", "")
        if url and url not in present:
            profile.sources.append(
                EntitySource(
                    source_url=url,
                    source_title=record.get("source_title", ""),
                    source_domain=record.get("source_domain", ""),
                    evidence_text=record.get("evidence_text", ""),
                )
            )
            present.add(url)
            restored += 1
    return restored


def main() -> None:
    parser = build_parser(__doc__)
    parser.add_argument("--mock-llm", action="store_true", help="use canned outputs (no server)")
    parser.add_argument("--entity", default=None, help="process only this canonical name")
    args = parser.parse_args()
    settings = load_settings(args.config_dir)
    ensure_data_dirs()

    groups = read_jsonl(GROUPS_PATH)
    if args.entity:
        groups = [g for g in groups if g["canonical_name"] == args.entity]
    done = {row.get("group_id") for row in iter_jsonl(ENTITIES_RAW_PATH)}
    pending = [g for g in groups if g["group_id"] not in done]
    if args.limit:
        pending = pending[: args.limit]

    log.info("%d groups, %d already merged, %d to merge", len(groups), len(done), len(pending))
    if args.dry_run or not pending:
        if args.dry_run:
            log.info("[dry-run] stopping before merging")
        return

    try:
        client = get_llm_client(settings, mock=args.mock_llm)
    except LLMError as exc:
        log.error("%s", exc)
        sys.exit(1)

    today = dt.date.today().isoformat()
    for group in pending:
        trimmed = [
            {k: v for k, v in record.items() if k not in _STAMP_FIELDS}
            for record in group["records"]
        ]
        try:
            profile: EntityWikiProfile = client.generate(
                EntityWikiProfile, build_merge_prompt(trimmed)
            )
        except Exception as exc:  # noqa: BLE001 - per-group isolation
            log.warning("entity=%r merge failed: %s", group["canonical_name"], exc)
            append_jsonl(
                ENTITIES_FAILED_PATH,
                [
                    {
                        "group_id": group["group_id"],
                        "canonical_name": group["canonical_name"],
                        "failure_stage": "generation",
                        "rejection_reasons": ["invalid_json"],
                        "error": str(exc)[:500],
                    }
                ],
            )
            continue

        if not profile.canonical_name:
            profile.canonical_name = group["canonical_name"]
        # every name variant seen in the group survives as an alias, including the
        # group's own canonical when the model chose a different one
        for alias in (*group["aliases"], group["canonical_name"]):
            if alias and alias not in profile.aliases and alias != profile.canonical_name:
                profile.aliases.append(alias)
        restored = _restore_dropped_sources(profile, group["records"])
        if restored:
            profile.notes = (profile.notes + " " if profile.notes else "") + (
                f"auto-restored {restored} source(s) dropped by the merge model"
            )

        stored = profile.model_dump()
        stored.update(
            {
                "group_id": group["group_id"],
                "source_count": len(profile.sources),
                "needs_review": group["needs_review"],
                "generated_by_model": getattr(client, "model_name", settings.qwen_model),
                "generation_date": today,
                "validation_status": "pending",
            }
        )
        append_jsonl(ENTITIES_RAW_PATH, [stored])
        log.info(
            "entity=%r merged from %d records, %d sources",
            profile.canonical_name,
            group["record_count"],
            len(profile.sources),
        )

    log.info("Done -> %s (validate with src.validation.validate_wiki_records next)", ENTITIES_RAW_PATH)


if __name__ == "__main__":
    main()

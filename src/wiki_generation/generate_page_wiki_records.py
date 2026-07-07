"""Stage 5, pass 1: one Qwen call per page input -> zero or more source-backed
wiki records appended to data/wiki/wiki_records_raw.jsonl.

Sequential with resume: pages already in pages_processed.jsonl are skipped on
rerun. A page whose generation fails is recorded in wiki_records_failed.jsonl
and NOT marked processed, so reruns retry it. source_url/title/domain are always
stamped from the page input, never trusted from the model."""

import datetime as dt
import json
import sys

from src.common.cli import build_parser
from src.common.config import PAGE_INPUTS_DIR, WIKI_DIR, ensure_data_dirs, load_settings
from src.common.io_utils import append_jsonl, iter_jsonl
from src.common.logging_setup import get_logger
from src.validation.validate_wiki_records import (
    clean_related_organizations,
    normalize_record,
    stamp_currency,
)
from src.validation.wiki_schema import PageRecordsResponse, PageWikiRecord, make_wiki_id
from src.wiki_generation.llm_client import LLMError, get_llm_client
from src.wiki_generation.qwen_page_wiki_prompt import build_prompt

log = get_logger("wiki_generation.generate_page_wiki_records", "wiki_generation.log")

RAW_PATH = WIKI_DIR / "wiki_records_raw.jsonl"
FAILED_PATH = WIKI_DIR / "wiki_records_failed.jsonl"
PROCESSED_PATH = WIKI_DIR / "pages_processed.jsonl"


def main() -> None:
    parser = build_parser(__doc__)
    parser.add_argument("--mock-llm", action="store_true", help="use canned outputs (no server)")
    parser.add_argument("--pages", default=None, help="comma-separated page ids to process")
    args = parser.parse_args()
    settings = load_settings(args.config_dir)
    ensure_data_dirs()

    processed = {row["page_id"] for row in iter_jsonl(PROCESSED_PATH)}
    inputs = sorted(PAGE_INPUTS_DIR.glob("page_*.json"))
    if args.pages:
        wanted = {p.strip() for p in args.pages.split(",")}
        inputs = [p for p in inputs if p.stem in wanted]
    pending = [p for p in inputs if p.stem not in processed]
    if args.limit:
        pending = pending[: args.limit]

    log.info("%d page inputs, %d already processed, %d to generate", len(inputs), len(processed), len(pending))
    if args.dry_run or not pending:
        if args.dry_run:
            log.info("[dry-run] stopping before generation")
        return

    try:
        client = get_llm_client(settings, mock=args.mock_llm)
    except LLMError as exc:
        log.error("%s", exc)
        sys.exit(1)

    today = dt.date.today().isoformat()
    total_records = 0
    for path in pending:
        page_input = json.loads(path.read_text(encoding="utf-8"))
        page_id = page_input["page_id"]
        try:
            response: PageRecordsResponse = client.generate(
                PageRecordsResponse, build_prompt(page_input, settings)
            )
        except Exception as exc:  # noqa: BLE001 - per-page isolation
            log.warning("page=%s generation failed: %s", page_id, exc)
            append_jsonl(
                FAILED_PATH,
                [
                    {
                        "page_id": page_id,
                        "source_url": page_input.get("source_url", ""),
                        "failure_stage": "generation",
                        "rejection_reasons": ["invalid_json"],
                        "error": str(exc)[:500],
                    }
                ],
            )
            continue

        records = []
        for llm_record in response.records:
            record = PageWikiRecord(
                **llm_record.model_dump(),
                page_id=page_id,
                generated_by_model=getattr(client, "model_name", settings.qwen_model),
                generation_date=today,
                validation_status="pending",
            )
            record.source_url = page_input.get("source_url", "")
            record.source_title = page_input.get("source_title", "")
            record.source_domain = page_input.get("source_domain", "")
            # Provenance + publication date are stamped from the page input, never
            # trusted from the model; currency is then computed deterministically.
            record.publication_date = (page_input.get("publication_date") or "").strip()
            record.date_precision = (page_input.get("date_precision") or "none").strip()
            record.wiki_id = make_wiki_id(record.source_url, record.entity_name, record.evidence_text)
            data = record.model_dump()
            clean_related_organizations(data)
            normalize_record(data, settings)
            stamp_currency(data, settings)
            records.append(data)

        append_jsonl(RAW_PATH, records)
        append_jsonl(PROCESSED_PATH, [{"page_id": page_id, "record_count": len(records)}])
        total_records += len(records)
        log.info("page=%s -> %d records", page_id, len(records))

    log.info("Done: %d records from %d pages -> %s", total_records, len(pending), RAW_PATH)


if __name__ == "__main__":
    main()

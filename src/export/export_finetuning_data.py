"""Optional Stage 8: build a LLaMA-Factory-style instruction dataset from
VALIDATED entity profiles only (never from raw crawled pages or source-less
claims — spec Stage 8 rules) -> data/exports/fine_tuning_candidates.jsonl."""

from src.common.cli import build_parser
from src.common.config import EXPORTS_DIR, WIKI_DIR, ensure_data_dirs, load_settings
from src.common.io_utils import read_jsonl, write_jsonl
from src.common.logging_setup import get_logger

log = get_logger("export.export_finetuning_data", "validation.log")

ENTITIES_VALIDATED_PATH = WIKI_DIR / "wiki_entities_validated.jsonl"
OUT_PATH = EXPORTS_DIR / "fine_tuning_candidates.jsonl"


def build_examples(entity: dict) -> list[dict]:
    name = entity.get("canonical_name", "")
    overview = (entity.get("overview") or "").strip()
    sources = [s.get("source_url", "") for s in entity.get("sources", []) if s.get("source_url")]
    if not name or not overview or not sources:
        return []

    # Anchor every target in time so the model doesn't learn a dated announcement
    # as a present-tense fact. currency flags how fresh that information is.
    currency = (entity.get("currency") or "").strip()
    pub_range = (entity.get("publication_date_range") or "").strip()
    temporal_bits = []
    if pub_range:
        temporal_bits.append(f"as of {pub_range}")
    if currency and currency != "fresh":
        temporal_bits.append(f"currency: {currency}")
    temporal = f" ({'; '.join(temporal_bits)})" if temporal_bits else ""
    source_line = f"{temporal} Source: {sources[0]}"
    examples = [
        {
            "instruction": f"What does {name} do in Georgia's EV supply chain?",
            "input": "",
            "output": overview + source_line,
        }
    ]
    locations = entity.get("locations") or []
    if locations:
        examples.append(
            {
                "instruction": f"Where does {name} operate in Georgia?",
                "input": "",
                "output": f"{name} operates in {', '.join(locations)} based on the sources.{source_line}",
            }
        )
    return examples


def main() -> None:
    args = build_parser(__doc__).parse_args()
    load_settings(args.config_dir)
    ensure_data_dirs()

    entities = read_jsonl(ENTITIES_VALIDATED_PATH)
    if args.limit:
        entities = entities[: args.limit]
    examples = [example for entity in entities for example in build_examples(entity)]

    if args.dry_run:
        log.info("[dry-run] would export %d fine-tuning examples from %d entities", len(examples), len(entities))
        return
    write_jsonl(OUT_PATH, examples)
    log.info("Exported %d fine-tuning examples from %d entities -> %s", len(examples), len(entities), OUT_PATH)


if __name__ == "__main__":
    main()

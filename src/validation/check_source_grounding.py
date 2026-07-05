"""Source-grounding check (spec Stage 6): evidence_text must actually appear in
the source page's Markdown — whitespace-normalized substring match, with a
rapidfuzz partial_ratio fallback because LLMs lightly paraphrase (exact-only
would reject good records).

Importable is_grounded(); as a CLI it re-verifies every validated entity's
sources against the crawled pages and demotes entities with no grounded source."""

import json
import re

from src.common.cli import build_parser
from src.common.config import PAGE_INPUTS_DIR, WIKI_DIR, load_settings
from src.common.io_utils import read_jsonl, write_jsonl
from src.common.logging_setup import get_logger

log = get_logger("validation.check_source_grounding", "validation.log")

ENTITIES_VALIDATED_PATH = WIKI_DIR / "wiki_entities_validated.jsonl"
ENTITIES_FAILED_PATH = WIKI_DIR / "wiki_entities_failed.jsonl"


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def is_grounded(evidence_text: str, page_markdown: str, threshold: int = 85) -> bool:
    evidence = _normalize_ws(evidence_text)
    page = _normalize_ws(page_markdown)
    if not evidence or not page:
        return False
    if evidence in page:
        return True
    from rapidfuzz import fuzz

    return fuzz.partial_ratio(evidence, page) >= threshold


def load_markdown_by_url() -> dict[str, str]:
    """source_url -> page markdown, from the Stage 5 page inputs."""
    pages = {}
    for path in PAGE_INPUTS_DIR.glob("page_*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("source_url"):
            pages[data["source_url"]] = data.get("page_markdown", "")
    return pages


def main() -> None:
    args = build_parser(__doc__).parse_args()
    settings = load_settings(args.config_dir)
    threshold = int(settings.wiki_schema.get("evidence_fuzzy_threshold", 85))

    markdown_by_url = load_markdown_by_url()
    entities = read_jsonl(ENTITIES_VALIDATED_PATH)
    kept, demoted = [], []
    for entity in entities:
        grounded_sources, ungrounded = [], []
        for source in entity.get("sources", []):
            page = markdown_by_url.get(source.get("source_url", ""), "")
            if is_grounded(source.get("evidence_text", ""), page, threshold):
                grounded_sources.append(source)
            else:
                ungrounded.append(source.get("source_url", ""))
        if grounded_sources:
            if ungrounded:
                entity.setdefault("conflicts_or_uncertainties", []).append(
                    f"ungrounded evidence for sources: {', '.join(filter(None, ungrounded))}"
                )
            kept.append(entity)
        else:
            entity["validation_status"] = "failed"
            entity["rejection_reasons"] = ["unsupported_claim"]
            demoted.append(entity)

    if args.dry_run:
        log.info("[dry-run] %d entities grounded, %d would be demoted", len(kept), len(demoted))
        return
    write_jsonl(ENTITIES_VALIDATED_PATH, kept)
    if demoted:
        existing_failed = read_jsonl(ENTITIES_FAILED_PATH)
        write_jsonl(ENTITIES_FAILED_PATH, existing_failed + demoted)
    log.info(
        "Grounding: %d entities kept, %d demoted (unsupported_claim)", len(kept), len(demoted)
    )


if __name__ == "__main__":
    main()

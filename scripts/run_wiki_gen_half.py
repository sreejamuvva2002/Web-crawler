"""Run Stage 5 page-wiki generation for one half of the corpus, writing to its
own half-specific output files so two halves can run concurrently against the
same repo without interleaving writes to the same JSONL file. Merge the two
halves' outputs into the real data/wiki files when both finish.

Usage: python3 scripts/run_wiki_gen_half.py <a|b>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.wiki_generation.generate_page_wiki_records as gpr
from src.common.config import WIKI_DIR

half = sys.argv[1]
assert half in ("a", "b")

pages_file = WIKI_DIR / f"_half_{half}_pages.txt"
pages = pages_file.read_text().strip()

gpr.RAW_PATH = WIKI_DIR / f"wiki_records_raw.half_{half}.jsonl"
gpr.FAILED_PATH = WIKI_DIR / f"wiki_records_failed.half_{half}.jsonl"
gpr.PROCESSED_PATH = WIKI_DIR / f"pages_processed.half_{half}.jsonl"

sys.argv = ["generate_page_wiki_records", "--pages", pages]
gpr.main()

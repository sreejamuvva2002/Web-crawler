from src.validation.check_source_grounding import is_grounded
from src.validation.remove_duplicate_facts import dedupe_records

PAGE = """# Georgia Battery Plant
Example Battery Company announced a $200 million battery materials facility
in Bryan County, Georgia, creating 350 jobs."""


def test_exact_substring_grounded():
    assert is_grounded("Example Battery Company announced a $200 million battery materials facility", PAGE)


def test_whitespace_and_case_tolerant():
    evidence = "example battery company ANNOUNCED a $200 million\n battery materials facility"
    assert is_grounded(evidence, PAGE)


def test_light_paraphrase_within_threshold():
    evidence = "Example Battery Company announced a $200 million battery materials facility in Bryan County Georgia creating 350 jobs"
    assert is_grounded(evidence, PAGE, threshold=85)


def test_fabricated_claim_rejected():
    assert not is_grounded("The company opened a gigafactory in Nevada with 5,000 workers.", PAGE)
    assert not is_grounded("", PAGE)


def test_dedupe_records_drops_same_fact():
    record = {"source_url": "https://x.com/1", "entity_name": "Acme", "evidence_text": "Acme built a plant."}
    same = {"source_url": "https://x.com/1", "entity_name": "acme", "evidence_text": "Acme  built a plant."}
    other = {"source_url": "https://x.com/2", "entity_name": "Acme", "evidence_text": "Acme built a plant."}
    kept, dropped = dedupe_records([record, same, other])
    assert len(kept) == 2 and len(dropped) == 1
    assert "duplicate_record" in dropped[0]["rejection_reasons"]

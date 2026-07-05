from src.validation.wiki_schema import (
    EntityWikiProfile,
    PageRecordsResponse,
    PageWikiRecordLLM,
    make_wiki_id,
)


def test_wiki_id_deterministic():
    a = make_wiki_id("https://x.com/1", "Acme", "Acme announced a plant.")
    b = make_wiki_id("https://x.com/1", "Acme", "Acme announced a plant.")
    assert a == b and len(a) == 16
    assert a != make_wiki_id("https://x.com/2", "Acme", "Acme announced a plant.")


def test_lenient_coercions():
    record = PageWikiRecordLLM(
        entity_name="Acme",
        jobs=350,
        investment_amount=200000000,
        summary=None,
        products_or_services=["batteries", 42],
        confidence_score="1.7",
    )
    assert record.jobs == "350"
    assert record.investment_amount == "200000000"
    assert record.summary == ""
    assert record.products_or_services == ["batteries", "42"]
    assert record.confidence_score == 1.0


def test_confidence_clamped_low_and_garbage():
    assert PageWikiRecordLLM(confidence_score=-3).confidence_score == 0.0
    assert PageWikiRecordLLM(confidence_score="n/a").confidence_score == 0.0


def test_empty_records_response():
    assert PageRecordsResponse().records == []


def test_entity_profile_string_to_list():
    profile = EntityWikiProfile(canonical_name="Acme", aliases="ACME Inc")
    assert profile.aliases == ["ACME Inc"]

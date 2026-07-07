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
        details=200000000,
        overview=None,
        confidence_score="1.7",
    )
    assert record.details == "200000000"
    assert record.overview == ""
    assert record.confidence_score == 1.0


def test_confidence_clamped_low_and_garbage():
    assert PageWikiRecordLLM(confidence_score=-3).confidence_score == 0.0
    assert PageWikiRecordLLM(confidence_score="n/a").confidence_score == 0.0


def test_empty_records_response():
    assert PageRecordsResponse().records == []


def test_entity_profile_string_to_list():
    profile = EntityWikiProfile(canonical_name="Acme", aliases="ACME Inc")
    assert profile.aliases == ["ACME Inc"]


def test_structured_sections_parse():
    record = PageWikiRecordLLM(
        entity_name="Acme",
        facilities=[{"name": "Acme Plant", "county": "Jackson County"}],
        investment=[{"amount": "$1B", "date": "2020"}],
        jobs=[{"hiring_goal": "500", "hiring_areas": "production"}],
        related_organizations=[{"name": "Acme Parent Co", "role": "Parent company"}],
        key_facts="Acme is Georgia's largest widget maker",
    )
    assert record.facilities[0].name == "Acme Plant"
    assert record.investment[0].amount == "$1B"
    assert record.jobs[0].hiring_areas == ["production"]
    assert record.related_organizations[0].role == "Parent company"
    assert record.key_facts == ["Acme is Georgia's largest widget maker"]


def test_entity_profile_key_facts_string_to_list():
    profile = EntityWikiProfile(canonical_name="Acme", key_facts="fact one")
    assert profile.key_facts == ["fact one"]

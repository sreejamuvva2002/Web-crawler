"""Tests for the temporal-grounding / staleness hardening: deterministic
currency bucketing, missing-date handling, claim_status validation, related-link
cleanup, entity-level aggregation, publication-date extraction, and backward
compatibility of records that predate the new fields."""

from src.common.config import load_settings
from src.crawling.publication_date import (
    date_from_html,
    date_from_labeled_html,
    date_from_metadata,
    date_from_url,
    date_from_url_month,
    extract_publication_date,
    normalize_iso,
)
from src.validation.validate_wiki_records import (
    clean_related_organizations,
    compute_currency,
    normalize_entity,
    normalize_record,
    stamp_currency,
    stamp_entity_currency,
    validate_page_record,
)
from src.validation.wiki_schema import EntitySource, FacilityItem, PageWikiRecordLLM

SETTINGS = load_settings()
AS_OF = "2026-07-06"


def _valid_record(**overrides) -> dict:
    """A minimal record that passes validate_page_record, before overrides."""
    record = {
        "entity_name": "Acme Battery",
        "overview": "Acme Battery makes cells in Georgia.",
        "state": "Georgia",
        "ev_relevance": "Makes EV battery cells.",
        "entity_type": "company",
        "supply_chain_category": "battery_cell_manufacturing",
        "source_url": "https://x.com/1",
        "evidence_text": "Acme Battery operates in Georgia.",
        "confidence_score": 1.0,
    }
    record.update(overrides)
    return record


# ---------------------------------------------------------------- currency buckets

def test_currency_buckets_across_boundaries():
    assert compute_currency("2026-03-01", AS_OF, SETTINGS) == "fresh"   # ~4 months
    assert compute_currency("2025-07-06", AS_OF, SETTINGS) == "aging"   # exactly 12 months
    assert compute_currency("2024-07-06", AS_OF, SETTINGS) == "stale"   # exactly 24 months
    assert compute_currency("2022-11-11", AS_OF, SETTINGS) == "stale"   # FREYR announcement
    assert compute_currency("2026-06-30", AS_OF, SETTINGS) == "fresh"


def test_currency_undated_when_no_date():
    assert compute_currency("", AS_OF, SETTINGS) == "undated"
    assert compute_currency("not-a-date", AS_OF, SETTINGS) == "undated"


def test_currency_handles_partial_dates():
    assert compute_currency("2026", AS_OF, SETTINGS) in {"fresh", "aging"}
    assert compute_currency("2023-01", AS_OF, SETTINGS) == "stale"


def test_stamp_currency_missing_date_is_undated_not_failure():
    record = _valid_record()  # no publication_date at all
    stamp_currency(record, SETTINGS)
    assert record["currency"] == "undated"
    assert record["as_of"]
    # crucially, a missing date is NOT a validation failure
    assert validate_page_record(record, SETTINGS) == []


def test_stamp_currency_uses_generation_date_as_default_anchor():
    record = _valid_record(publication_date="2020-01-01", generation_date="2026-07-06")
    stamp_currency(record, SETTINGS)
    assert record["as_of"] == "2026-07-06"
    assert record["currency"] == "stale"


# ------------------------------------------------------------- claim_status checks

def test_valid_claim_status_passes():
    for status in ("announced", "under_construction", "operational"):
        assert validate_page_record(_valid_record(claim_status=status), SETTINGS) == []


def test_invalid_claim_status_rejected():
    assert "invalid_claim_status" in validate_page_record(
        _valid_record(claim_status="bogus"), SETTINGS
    )


def test_empty_claim_status_allowed():
    assert "invalid_claim_status" not in validate_page_record(
        _valid_record(claim_status=""), SETTINGS
    )


# ------------------------------------------------------------ related-link cleanup

def test_related_link_cleanup_drops_chrome():
    record = {
        "related_organizations": [
            {"name": "SK On", "role": "Parent company", "source": "body"},
            {"name": "General Carden", "role": "official", "source": "related_link"},
            {"name": "SK Innovation", "details": "referenced in related links"},
            {"name": "Press Office", "role": "media contact"},
        ]
    }
    dropped = clean_related_organizations(record)
    kept = [o["name"] for o in record["related_organizations"]]
    assert dropped == 3
    assert kept == ["SK On"]


def test_related_link_cleanup_noop_on_clean_record():
    record = {"related_organizations": [{"name": "Ford", "role": "Automaker customer"}]}
    assert clean_related_organizations(record) == 0
    assert len(record["related_organizations"]) == 1


def test_related_link_cleanup_drops_publishers_and_distributors():
    # Regression: govtech policy page_000009 leaked the byline outlet and its
    # syndicator into related_organizations.
    record = {
        "related_organizations": [
            {"name": "Rivian", "role": "EV manufacturer announcing a Georgia factory"},
            {"name": "Atlanta Journal-Constitution", "role": "Publication of the article (source)"},
            {"name": "Tribune Content Agency, LLC", "role": "Distributor of the article"},
        ]
    }
    dropped = clean_related_organizations(record)
    kept = [o["name"] for o in record["related_organizations"]]
    assert dropped == 2
    assert kept == ["Rivian"]


# --------------------------------------------------------- entity-level aggregation

def test_entity_currency_reflects_freshest_source():
    profile = {
        "sources": [
            {"publication_date": "2018-05-01", "claim_status": "announced"},
            {"publication_date": "2026-03-01", "claim_status": "operational"},
        ]
    }
    stamp_entity_currency(profile, SETTINGS, as_of=AS_OF)
    assert profile["currency"] == "fresh"  # newest info is 2026-03
    assert profile["publication_date_range"] == "2018-05-01 .. 2026-03-01"
    assert profile["claim_status"] == "operational"  # most-advanced across sources


def test_entity_currency_undated_without_source_dates():
    profile = {"sources": [{"source_url": "https://x.com/1"}]}
    stamp_entity_currency(profile, SETTINGS, as_of=AS_OF)
    assert profile["currency"] == "undated"
    assert profile["publication_date_range"] == ""


def test_entity_does_not_override_explicit_claim_status():
    profile = {
        "claim_status": "cancelled",  # set by a later reconciliation step
        "sources": [{"publication_date": "2022-11-11", "claim_status": "announced"}],
    }
    stamp_entity_currency(profile, SETTINGS, as_of=AS_OF)
    assert profile["claim_status"] == "cancelled"  # not clobbered by aggregation


# --------------------------------------------------------- old-record compatibility

def test_old_record_without_new_fields_still_validates():
    # A record shaped like the pre-change corpus (no claim_status/currency/date).
    old = _valid_record()
    old.pop("confidence_score", None)
    old["confidence_score"] = 0.9
    assert validate_page_record(old, SETTINGS) == []


# -------------------------------------------------- deterministic normalization

def test_county_suffix_normalization():
    record = _valid_record(county="Jackson", facilities=[{"county": "Coweta"}, {"county": "Bibb County"}])
    normalize_record(record, SETTINGS)
    assert record["county"] == "Jackson County"
    assert [f["county"] for f in record["facilities"]] == ["Coweta County", "Bibb County"]


def test_confidence_capped_pre_validation():
    record = _valid_record(confidence_score=1.0)
    normalize_record(record, SETTINGS)
    assert record["confidence_score"] == 0.95
    # a modest confidence is left untouched
    record2 = _valid_record(confidence_score=0.8)
    normalize_record(record2, SETTINGS)
    assert record2["confidence_score"] == 0.8


def test_normalize_entity_counties_and_confidence():
    profile = {"confidence_score": 1.0, "facilities": [{"county": "Coweta"}]}
    normalize_entity(profile, SETTINGS)
    assert profile["confidence_score"] == 0.95
    assert profile["facilities"][0]["county"] == "Coweta County"


# ------------------------------------------------------------- new schema fields

def test_facility_count_field_and_default():
    assert FacilityItem().count == ""
    assert FacilityItem(name="Commerce Plants", count="2").count == "2"


def test_evidence_snippets_parse_on_record_and_source():
    rec = PageWikiRecordLLM(entity_name="Acme", evidence_snippets=["a", "b"])
    assert rec.evidence_snippets == ["a", "b"]
    assert PageWikiRecordLLM(evidence_snippets="single").evidence_snippets == ["single"]
    assert EntitySource(evidence_snippets="q").evidence_snippets == ["q"]


# ------------------------------------------------------ publication-date extraction

def test_normalize_iso_variants():
    assert normalize_iso("2023-01-30T09:00:00Z") == "2023-01-30"
    assert normalize_iso("2023-05") == "2023-05-01"
    assert normalize_iso("2023") == "2023-01-01"
    assert normalize_iso("no date") == ""


def test_date_from_url_path():
    assert date_from_url(
        "https://gov.georgia.gov/press-releases/2023-01-30/gov-kemp-sk"
    ) == "2023-01-30"
    assert date_from_url("https://example.com/news/story") == ""


def test_date_from_html_and_metadata():
    assert date_from_html(
        '<meta property="article:published_time" content="2023-01-30T09:00Z">'
    ) == "2023-01-30"
    assert date_from_html('{"datePublished":"2022-11-05T00:00:00"}') == "2022-11-05"
    assert date_from_metadata({"og:published_time": "2020-02-02T10:00:00"}) == "2020-02-02"


def test_extract_publication_date_precision():
    assert extract_publication_date(
        url="https://x.com/a", metadata={"article:published_time": "2021-06-15"}
    ) == ("2021-06-15", "html_meta")
    assert extract_publication_date(url="https://x.com/2019/03/15/a") == ("2019-03-15", "url_path")
    assert extract_publication_date(url="https://x.com/story") == ("", "none")


def test_date_from_labeled_html_published_label():
    # Visible "Published" label whose date sits outside <head> meta and past the
    # first 2000 chars (regression: govtech page_000009 "June 05, 2025").
    html = "<nav>" + ("x" * 3000) + '</nav><span aria-label="Published">June 05, 2025</span>'
    assert date_from_labeled_html(html) == "2025-06-05"
    assert date_from_labeled_html("<div>Posted on May 20, 2022 by staff</div>") == "2022-05-20"
    assert date_from_labeled_html("<p>Published:</p> <time>2022-11-11</time>") == "2022-11-11"


def test_date_from_labeled_html_bare_time_element():
    # <time> with no datetime attribute, text-only (regression: ossoff page_000010).
    html = '<span class="post-info__item--type-date"><time>May 20, 2022</time></span>'
    assert date_from_labeled_html(html) == "2022-05-20"


def test_date_from_labeled_html_ignores_updated_only():
    # "Updated" is not a publication signal; no publish/posted label -> nothing.
    assert date_from_labeled_html("<div>Updated March 3, 2024</div>") == ""
    assert date_from_labeled_html("") == ""


def test_extract_publication_date_body_label_precision():
    html = '<span aria-label="Published">June 05, 2025</span>'
    assert extract_publication_date(html=html) == ("2025-06-05", "body_dateline")


def test_url_month_precision():
    # Year+month URL segment with no day -> coarse YYYY-MM at url_path_month precision.
    assert date_from_url_month("https://savannahjda.com/2022/11/hyundai-mobis/") == "2022-11"
    assert date_from_url_month("https://x.com/story") == ""
    assert extract_publication_date(url="https://x.com/2022/11/slug") == ("2022-11", "url_path_month")
    # A full date still wins over month precision.
    assert extract_publication_date(url="https://x.com/2019/03/15/a") == ("2019-03-15", "url_path")

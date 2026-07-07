"""Pydantic models for wiki records (page-level and entity-level).

One primary entity per source page: a page's record covers whichever company,
facility, project, program, etc. the page is centrally about. Everyone else
mentioned on the page (parent/subsidiary companies, OEM customers, contractors,
agencies, named people) is folded into related_organizations/workforce_programs
on that one record rather than becoming a record of its own. They still get
their own dedicated wiki page later if some other crawled page is actually
about them.

Parsing is deliberately lenient — LLM output with a wrong category or a numeric
jobs value still parses (coerced to str). Strict enforcement of allowed values,
required fields, and grounding happens in the validation stage, which labels
failures with the spec's rejection reasons instead of crashing the parse."""

import hashlib

from pydantic import BaseModel, ConfigDict, Field, field_validator


def make_wiki_id(source_url: str, entity_name: str, evidence_text: str) -> str:
    """Deterministic id so reruns produce the same record identity (natural dedup)."""
    key = f"{source_url}|{entity_name}|{evidence_text[:100]}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


class _LenientModel(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True, extra="ignore")

    @field_validator("*", mode="before")
    @classmethod
    def _none_to_empty(cls, value, info):
        if value is None:
            annotation = str(cls.model_fields[info.field_name].annotation)
            return [] if annotation.startswith("list") else ""
        return value


class FacilityItem(_LenientModel):
    name: str = ""
    location: str = ""
    county: str = ""
    status: str = ""
    capacity: str = ""
    # When the page states a count of facilities ("two plants") but does not name
    # them individually, use ONE entry with count set — do not invent per-facility
    # names. "" or "1" for a single named facility.
    count: str = ""
    details: str = ""


class InvestmentItem(_LenientModel):
    amount: str = ""
    date: str = ""
    purpose: str = ""
    # "entity" = this Georgia entity/project's own investment; "company_wide" =
    # a global/corporate boilerplate figure (e.g. a parent's worldwide roadmap);
    # "context" = a background figure for a DIFFERENT entity, mentioned only as
    # context (common on policy/news pages, e.g. another automaker's investment).
    scope: str = "entity"
    details: str = ""


class JobsEntry(_LenientModel):
    hiring_goal: str = ""
    timeline: str = ""
    hiring_areas: list[str] = []
    details: str = ""

    @field_validator("hiring_areas", mode="before")
    @classmethod
    def _stringify_items(cls, value):
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        if isinstance(value, str) and value:
            return [value]
        return value


class WorkforceProgram(_LenientModel):
    name: str = ""
    relationship: str = ""
    details: str = ""


class RelatedOrganization(_LenientModel):
    name: str = ""
    role: str = ""
    # "body" = a real entity from the article body with a genuine relationship;
    # "related_link" = navigational chrome (Related Links / More News / press
    # contacts / sidebar) that must be demoted, not treated as entity data.
    source: str = "body"
    details: str = ""


class TimelineEvent(_LenientModel):
    date: str = ""
    event: str = ""
    # "entity" = a dated event for this Georgia entity/project; "company_wide" =
    # a global/corporate roadmap date (e.g. a parent's worldwide GWh targets);
    # "context" = a background event about a DIFFERENT entity, mentioned only as
    # context (common on policy/news pages, e.g. "Rivian announced a plant in 2021").
    scope: str = "entity"


class PageWikiRecordLLM(_LenientModel):
    """The page-level record schema — exactly what the model returns per record,
    one record per primary entity on the page (almost always exactly one)."""

    entity_name: str = ""
    canonical_name: str = ""
    entity_type: str = ""
    title: str = ""
    overview: str = ""
    # location/county/state describe the GEORGIA project/facility this page is
    # about (where the investment/jobs/facility are) — NOT the company's HQ.
    location: str = ""
    county: str = ""
    state: str = "Georgia"
    country: str = "United States"
    # The primary entity's corporate headquarters, when the page states it and it
    # differs from the Georgia project location (e.g. "Chicago, Illinois").
    headquarters: str = ""
    ev_relevance: str = ""
    supply_chain_category: str = ""
    source_url: str = ""
    source_title: str = ""
    source_domain: str = ""
    evidence_text: str = ""
    # Short supporting quotes/paraphrases covering the different facets that
    # evidence_text alone can't (location, investment, jobs, capacity, partners,
    # workforce, status) — broadens grounding coverage of the extraction.
    evidence_snippets: list[str] = []
    # Extraction/source-grounding reliability ONLY — never currency. The model
    # scores this; it does not judge whether the facts are still true today.
    confidence_score: float = Field(default=0.0)
    # Status as represented on THIS source page: announced | under_construction |
    # operational. Never cancelled/superseded (a single announcement can't know it).
    claim_status: str = ""
    facilities: list[FacilityItem] = []
    investment: list[InvestmentItem] = []
    jobs: list[JobsEntry] = []
    workforce_programs: list[WorkforceProgram] = []
    related_organizations: list[RelatedOrganization] = []
    timeline: list[TimelineEvent] = []
    key_facts: list[str] = []
    details: str = ""

    @field_validator("confidence_score", mode="before")
    @classmethod
    def _clamp_confidence(cls, value):
        try:
            return min(max(float(value or 0.0), 0.0), 1.0)
        except (TypeError, ValueError):
            return 0.0

    @field_validator("key_facts", "evidence_snippets", mode="before")
    @classmethod
    def _stringify_items(cls, value):
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        if isinstance(value, str) and value:
            return [value]
        return value


class PageRecordsResponse(BaseModel):
    """Object root for JSON mode / vLLM guided_json (an array root is fragile)."""

    records: list[PageWikiRecordLLM] = []


class PageWikiRecord(PageWikiRecordLLM):
    """Stored form: LLM record + pipeline stamps.

    publication_date/date_precision are stamped from crawl metadata (never the
    model); currency/as_of are computed deterministically in the validation stage.
    They live here, not on PageWikiRecordLLM, so the model is never asked for them."""

    wiki_id: str = ""
    page_id: str = ""
    generated_by_model: str = ""
    generation_date: str = ""
    # Real publication date of the source page (ISO YYYY-MM-DD), "" if unknown.
    publication_date: str = ""
    date_precision: str = ""  # html_meta | url_path | none
    # Deterministic freshness bucket computed from publication_date vs as_of.
    currency: str = ""        # fresh | aging | stale | undated
    as_of: str = ""           # date the currency bucket was computed against
    validation_status: str = "pending"


class EntitySource(_LenientModel):
    source_url: str = ""
    source_title: str = ""
    source_domain: str = ""
    publication_date: str = ""
    claim_status: str = ""
    evidence_text: str = ""
    evidence_snippets: list[str] = []

    @field_validator("evidence_snippets", mode="before")
    @classmethod
    def _stringify_items(cls, value):
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        if isinstance(value, str) and value:
            return [value]
        return value


class EntityWikiProfile(_LenientModel):
    """The entity-level profile merged across every page about this one primary
    entity. Structured sections mirror PageWikiRecordLLM's, combined across all
    of the entity's source pages."""

    canonical_name: str = ""
    aliases: list[str] = []
    entity_type: str = ""
    title: str = ""
    overview: str = ""
    locations: list[str] = []
    headquarters: str = ""
    supply_chain_categories: list[str] = []
    facilities: list[FacilityItem] = []
    investment: list[InvestmentItem] = []
    jobs: list[JobsEntry] = []
    workforce_programs: list[WorkforceProgram] = []
    related_organizations: list[RelatedOrganization] = []
    timeline: list[TimelineEvent] = []
    key_facts: list[str] = []
    sources: list[EntitySource] = []
    confidence_score: float = Field(default=0.0)
    # Temporal grounding aggregated across the entity's source pages.
    publication_date_range: str = ""  # "earliest .. latest" of source pub dates
    claim_status: str = ""            # latest/most-advanced status across sources
    currency: str = ""               # bucket for the freshest source (newest info we have)
    as_of: str = ""
    conflicts_or_uncertainties: list[str] = []
    details: str = ""

    @field_validator("confidence_score", mode="before")
    @classmethod
    def _clamp_confidence(cls, value):
        try:
            return min(max(float(value or 0.0), 0.0), 1.0)
        except (TypeError, ValueError):
            return 0.0

    @field_validator(
        "aliases",
        "locations",
        "supply_chain_categories",
        "key_facts",
        "conflicts_or_uncertainties",
        mode="before",
    )
    @classmethod
    def _stringify_items(cls, value):
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        if isinstance(value, str) and value:
            return [value]
        return value

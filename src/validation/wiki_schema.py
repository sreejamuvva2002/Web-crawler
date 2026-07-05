"""Pydantic models for wiki records (page-level and entity-level).

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


class PageWikiRecordLLM(_LenientModel):
    """The spec's page-level record schema — exactly what Qwen returns per record."""

    entity_type: str = ""
    entity_name: str = ""
    canonical_name: str = ""
    summary: str = ""
    location: str = ""
    county: str = ""
    state: str = "Georgia"
    country: str = "United States"
    ev_relevance: str = ""
    supply_chain_category: str = ""
    products_or_services: list[str] = []
    customers_or_oems: list[str] = []
    investment_amount: str = ""
    jobs: str = ""
    facility_status: str = ""
    dates_mentioned: list[str] = []
    source_url: str = ""
    source_title: str = ""
    source_domain: str = ""
    evidence_text: str = ""
    confidence_score: float = Field(default=0.0)
    notes: str = ""

    @field_validator("confidence_score", mode="before")
    @classmethod
    def _clamp_confidence(cls, value):
        try:
            return min(max(float(value or 0.0), 0.0), 1.0)
        except (TypeError, ValueError):
            return 0.0

    @field_validator("products_or_services", "customers_or_oems", "dates_mentioned", mode="before")
    @classmethod
    def _stringify_items(cls, value):
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        return value


class PageRecordsResponse(BaseModel):
    """Object root for JSON mode / vLLM guided_json (an array root is fragile)."""

    records: list[PageWikiRecordLLM] = []


class PageWikiRecord(PageWikiRecordLLM):
    """Stored form: LLM record + pipeline stamps."""

    wiki_id: str = ""
    page_id: str = ""
    generated_by_model: str = ""
    generation_date: str = ""
    validation_status: str = "pending"


class EntitySource(_LenientModel):
    source_url: str = ""
    source_title: str = ""
    source_domain: str = ""
    evidence_text: str = ""


class EntityWikiProfile(_LenientModel):
    """The spec's entity-level merged profile."""

    canonical_name: str = ""
    aliases: list[str] = []
    entity_type: str = ""
    summary: str = ""
    locations: list[str] = []
    supply_chain_categories: list[str] = []
    products_or_services: list[str] = []
    customers_or_oems: list[str] = []
    investment_amounts: list[str] = []
    jobs: list[str] = []
    facility_status: str = ""
    related_entities: list[str] = []
    sources: list[EntitySource] = []
    confidence_score: float = Field(default=0.0)
    conflicts_or_uncertainties: list[str] = []
    notes: str = ""

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
        "products_or_services",
        "customers_or_oems",
        "investment_amounts",
        "jobs",
        "related_entities",
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

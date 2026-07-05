"""The spec's entity-level merge prompt, verbatim (the return schema matches
EntityWikiProfile)."""

import json

ENTITY_MERGE_PROMPT_TEMPLATE = """You are merging validated source-backed wiki records into one entity-level LLM Wiki profile.

Use only the provided records.

Rules:
1. Do not add outside knowledge.
2. Preserve all source URLs.
3. Preserve evidence_text for each important claim.
4. Merge aliases only when the records clearly refer to the same entity.
5. If records conflict, keep both claims and mark the conflict in notes.
6. Do not remove source information.
7. Return valid JSON only.

Entity group:
{entity_group_records}

Return one JSON object using this schema:
{
  "canonical_name": "",
  "aliases": [],
  "entity_type": "",
  "summary": "",
  "locations": [],
  "supply_chain_categories": [],
  "products_or_services": [],
  "customers_or_oems": [],
  "investment_amounts": [],
  "jobs": [],
  "facility_status": "",
  "related_entities": [],
  "sources": [
    {
      "source_url": "",
      "source_title": "",
      "source_domain": "",
      "evidence_text": ""
    }
  ],
  "confidence_score": 0.0,
  "conflicts_or_uncertainties": [],
  "notes": ""
}"""


def build_merge_prompt(records: list[dict]) -> str:
    payload = json.dumps(records, ensure_ascii=False, indent=2)
    return ENTITY_MERGE_PROMPT_TEMPLATE.replace("{entity_group_records}", payload)

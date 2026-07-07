"""Stage 6's entity-level merge prompt. Combines the structured sections of every
page-level record about one primary entity (across all of its source pages)
into a single EntityWikiProfile."""

import json

ENTITY_MERGE_PROMPT_TEMPLATE = """You are merging validated source-backed wiki records into one entity-level LLM Wiki profile.

Every input record is a different source page's version of the same primary entity. Combine them into one profile.

Use only the provided records.

Rules:
1. Do not add outside knowledge.
2. Preserve all source URLs and their evidence_text in "sources" — one entry per input record's source_url.
3. Merge aliases only when the records clearly refer to the same entity.
4. If records conflict (e.g. two different job counts, two different capacities), keep both claims and note the conflict in conflicts_or_uncertainties instead of silently picking one.
5. Do not remove source information.
6. Return valid JSON only.
7. Combine each record's facilities, investment, jobs, workforce_programs, related_organizations, timeline, and key_facts lists into the entity's lists of the same name. De-duplicate restated facts, but keep genuinely different data points (e.g. two investment figures at two different dates, or a hiring goal and its later expansion) rather than dropping one.
8. Combine each record's "details" into the entity's "details" the same way — de-duplicated, but keeping distinct facts.
9. overview must be a full connective narrative paragraph (aim for 5-8 sentences across the combined records), not a short summary. It is where the relationships *between* facts belong — how the entity's facilities, investment, technology, partners, and programs connect to each other and to the entity's overall role — since the structured lists below necessarily break those same facts into separate parallel items. Synthesize across all of the entity's source pages into one coherent narrative, the way a human-written company profile would, not a bulleted recap of the structured sections.
10. title should be a short page title in the style "Entity Name" or "Entity Name — Project/Facility Name, County, Georgia".
11. For each "sources" entry, carry over that input record's publication_date and claim_status unchanged. Do not invent, alter, or blank them.
12. Preserve the "scope" tag ("entity" or "company_wide") on every timeline and investment item when merging — never relabel a company-wide global figure as an entity fact or vice versa.
13. Preserve each related_organizations entry's "source" tag. Do not include any entry whose source is "related_link"; only carry over real body-sourced entities.
14. Leave currency, as_of, and publication_date_range empty — they are computed automatically downstream, not by you. Set claim_status to the entity's most-advanced status across its sources (operational over under_construction over announced), or leave it empty if no source gives a status.
15. Preserve each facility's "count" when merging, and do not invent distinct facility names — if the records describe N unnamed facilities collectively, keep one entry with count set. Carry over capacity/status when any record provides them.
16. Keep county names in the "X County" form and location values specific (place, county, state) as given in the records — do not strip the county/state.
17. For each "sources" entry, carry over that input record's evidence_snippets as well. Do not drop them.
18. Do not add a stock exchange the entity is merely listed on, an index, or any non-partner reference to related_organizations — those belong in details. Likewise exclude press/communications contacts (press secretary, communications manager, spokesperson) and bare geographic locations (a city/state, or an "existing footprint" location) from related_organizations.
19. Carry over "headquarters" from the records. Keep the entity's Georgia project locations in "locations" and the corporate headquarters (if out-of-state) only in "headquarters" — never fold the HQ into locations.
20. Preserve exact figures and their qualifiers ("over $800 million", "more than $21.9 billion") when merging — do not round or drop "over"/"more than"/decimals.

Entity group:
{entity_group_records}

Return one JSON object using this schema:
{
  "canonical_name": "",
  "aliases": [],
  "entity_type": "",
  "title": "",
  "overview": "",
  "locations": [],
  "headquarters": "",
  "supply_chain_categories": [],
  "facilities": [{"name": "", "location": "", "county": "", "status": "", "capacity": "", "count": "", "details": ""}],
  "investment": [{"amount": "", "date": "", "purpose": "", "scope": "entity", "details": ""}],
  "jobs": [{"hiring_goal": "", "timeline": "", "hiring_areas": [], "details": ""}],
  "workforce_programs": [{"name": "", "relationship": "", "details": ""}],
  "related_organizations": [{"name": "", "role": "", "source": "body", "details": ""}],
  "timeline": [{"date": "", "event": "", "scope": "entity"}],
  "key_facts": [],
  "sources": [
    {
      "source_url": "",
      "source_title": "",
      "source_domain": "",
      "publication_date": "",
      "claim_status": "",
      "evidence_text": "",
      "evidence_snippets": []
    }
  ],
  "confidence_score": 0.0,
  "claim_status": "",
  "conflicts_or_uncertainties": [],
  "details": ""
}"""


def build_merge_prompt(records: list[dict]) -> str:
    payload = json.dumps(records, ensure_ascii=False, indent=2)
    return ENTITY_MERGE_PROMPT_TEMPLATE.replace("{entity_group_records}", payload)

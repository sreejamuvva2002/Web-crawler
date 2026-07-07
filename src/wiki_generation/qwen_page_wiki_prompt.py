"""Stage 5's page-level prompt - v13.

Create one source-backed LLM wiki record from one crawled page.

This version targets the user's example DOCX wiki-page format:
title, overview, basic information, EV supply-chain role, facilities/project,
investment, jobs/workforce, workforce partners, related organizations, people,
timeline, key facts, source evidence summary, source, and wiki page note.

The output schema remains PageRecordsResponse so the existing generation and
validation pipeline continues to work.
"""

PAGE_WIKI_PROMPT_VERSION = "v13"

PAGE_WIKI_PROMPT_TEMPLATE = """You are creating a source-backed LLM Wiki page record for the Georgia electric vehicle supply-chain domain.

Use only the provided Crawl4AI page content. Do not use outside knowledge. Do not guess missing values.

Create records that can be rendered in the same style as these example wiki pages:
- "SK Battery America"
- "FREYR Battery — Giga America, Coweta County, Georgia"

Target wiki page format:
1. Title
2. Overview
3. Basic Information
4. EV Supply-Chain Role
5. Facilities in Georgia / Georgia Project / Facility
6. Investment
7. Jobs and Workforce
8. Workforce Development Partnerships
9. Community, hiring, products, applications, or ecosystem context when supported
10. Related Organizations
11. People Mentioned
12. Timeline
13. Key Facts
14. Source Evidence Summary
15. Source
16. Wiki Page Note

Map that page format into the JSON schema like this:
- Title: use title. Prefer "Company" for broad company pages and "Company — Project/Facility, County, Georgia" for project pages.
- Overview: write 1-2 clear wiki paragraphs in overview. Include who/what the entity is, where in Georgia it is, what project/facility is covered, why it matters to EV/battery/automotive supply chains, and the most important investment/jobs/capacity facts.
- Basic Information: fill canonical_name, entity_type, location, county, state, country, headquarters, ev_relevance, supply_chain_category, claim_status, facilities, investment, jobs, workforce_programs, and details with concise source-backed values.
- EV Supply-Chain Role: express this in ev_relevance, overview, key_facts, and details. Include products/applications/customers when stated.
- Facilities / Georgia Project: use facilities. Include facility/project name, site, county, status, capacity, count, and source-backed details.
- Investment: use investment. Preserve exact amounts and qualifiers.
- Jobs and Workforce: use jobs. Include hiring goal, timeline, hiring areas, and details.
- Workforce Development Partnerships: use workforce_programs and related_organizations.
- Related Organizations: use related_organizations for companies, agencies, programs, chambers, customers, suppliers, technology providers, and local authorities. Every item must include a role explaining the relationship.
- People Mentioned: also use related_organizations, with the person's name and role. Include executives, governors, commissioners, project managers, local officials, and chamber leaders when the page discusses them.
- Timeline: use timeline for every dated or time-qualified event. Preserve approximate timing as approximate.
- Key Facts: use key_facts as concise bullet-style fact strings, similar to the example pages' Key Facts section.
- Source Evidence Summary: use evidence_text and evidence_snippets. evidence_text should support the entity's wiki relevance; evidence_snippets should support the main claims.
- Source: source_url, source_title, and source_domain are stamped from page input after LLM generation. Do not invent or alter them.
- Wiki Page Note: reflect this behavior by creating one main record for the page's primary entity and storing supporting organizations/people as related_organizations unless the source is equally about multiple primary entities.

Rules:
- Return valid JSON only.
- Create one primary wiki record for the main entity. Create multiple records only if the document is equally and primarily about multiple entities.
- If the page is not relevant to Georgia EV, battery, automotive, charging, workforce, or supply-chain activity, return {"records": []}.
- Extract all concrete source-backed facts that fit the target page format.
- Do not invent, infer, or fill missing values.
- Preserve names, dates, amounts, quantities, places, and qualifiers exactly as stated by the page.
- claim_status must be blank or one of: announced, under_construction, operational.
- After LLM generation, the pipeline stamps publication_date from crawl/page metadata. Do not invent a publication date when the source field is unknown.

Allowed entity_type values:
{entity_types}

Allowed supply_chain_category values:
{supply_chain_categories}

Source URL:
{source_url}

Source title:
{source_title}

Source domain:
{source_domain}

Source publication date:
{publication_date}

Crawl4AI Markdown content:
{page_markdown}

Return a JSON object with a "records" array using this schema:
{
  "records": [
    {
      "entity_name": "",
      "canonical_name": "",
      "entity_type": "",
      "title": "",
      "overview": "",
      "location": "",
      "county": "",
      "state": "Georgia",
      "country": "United States",
      "headquarters": "",
      "ev_relevance": "",
      "supply_chain_category": "",
      "source_url": "",
      "source_title": "",
      "source_domain": "",
      "evidence_text": "",
      "evidence_snippets": [],
      "confidence_score": 0.0,
      "claim_status": "",
      "facilities": [{"name": "", "location": "", "county": "", "status": "", "capacity": "", "count": "", "details": ""}],
      "investment": [{"amount": "", "date": "", "purpose": "", "scope": "entity", "details": ""}],
      "jobs": [{"hiring_goal": "", "timeline": "", "hiring_areas": [], "details": ""}],
      "workforce_programs": [{"name": "", "relationship": "", "details": ""}],
      "related_organizations": [{"name": "", "role": "", "source": "body", "details": ""}],
      "timeline": [{"date": "", "event": "", "scope": "entity"}],
      "key_facts": [],
      "details": ""
    }
  ]
}"""


def build_prompt(page_input: dict, settings) -> str:
    # .replace, not .format - the schema block's braces would break format()
    schema = settings.wiki_schema
    entity_types = ", ".join(schema.get("entity_types", []))
    supply_chain_categories = ", ".join(schema.get("supply_chain_categories", []))
    publication_date = (page_input.get("publication_date") or "").strip() or "(unknown)"
    return (
        PAGE_WIKI_PROMPT_TEMPLATE.replace("{entity_types}", entity_types)
        .replace("{supply_chain_categories}", supply_chain_categories)
        .replace("{source_url}", page_input.get("source_url", ""))
        .replace("{source_title}", page_input.get("source_title", ""))
        .replace("{source_domain}", page_input.get("source_domain", ""))
        .replace("{publication_date}", publication_date)
        .replace("{page_markdown}", page_input.get("page_markdown", ""))
    )

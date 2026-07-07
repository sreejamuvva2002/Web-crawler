"""Stage 5's page-level prompt - v15 (hybrid: JSON wrapper + flat fact list).

v15 optimizes for *recall / no lost meaning*. Instead of forcing every fact into
rigid sub-fields (facilities/investment/jobs/...) as v13 does, v15 keeps only a
light identity wrapper (entity name + type + category) plus one exhaustive flat
``facts`` list of self-contained bullet strings. Nothing gets squeezed into or
dropped by a schema; each fact is captured verbatim with its numbers, names,
dates, and qualifiers.

It still returns valid JSON (so it parses cleanly and provenance can be stamped),
but the substance lives in ``facts``. This does NOT feed the v13 structured
grouping/merge pipeline unchanged — it targets the LLM-Wiki markdown direction
and quick recall comparison against the v13 samples.
"""

from pydantic import BaseModel, Field

PAGE_WIKI_PROMPT_VERSION = "v15"


class Link(BaseModel):
    """A URL / contact / CTA pulled OUT of the fact text and kept separately, so
    the main facts list never contains raw links."""

    url: str = ""
    context: str = ""  # what it points to, e.g. "Careers page", "Company website"


class FactRecord(BaseModel):
    """One primary entity on the page plus every project-relevant fact about it."""

    entity_name: str = ""
    canonical_name: str = ""
    entity_type: str = ""
    supply_chain_category: str = ""
    facts: list[str] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    # Provenance is stamped from the page input after generation, never trusted
    # from the model. publication_date tells whether the info is fresh or stale;
    # date_precision records how it was derived (e.g. url_path, meta_tag).
    source_url: str = ""
    source_title: str = ""
    source_domain: str = ""
    publication_date: str = ""
    date_precision: str = ""


class FactRecordsResponse(BaseModel):
    records: list[FactRecord] = Field(default_factory=list)


PAGE_WIKI_PROMPT_TEMPLATE = """You are extracting facts for the Georgia electric vehicle (EV) supply-chain project from one crawled web page.

Use ONLY the provided Crawl4AI page content. Do not use outside knowledge. Do not guess, infer, or invent anything.

PRIMARY OBJECTIVE - EXHAUSTIVE FACT CAPTURE:
Capture EVERY project-relevant fact on the page as a separate bullet in the "facts" list, without losing meaning. Do not summarize the page down to a few highlights, and do not drop a fact because it seems minor, repeated, or awkward to categorize. If it is supported by the page and relevant to the project, it becomes its own fact string. Completeness beats brevity.

WHAT "RELEVANT TO OUR PROJECT" MEANS:
Anything about the Georgia (or Southeast U.S. battery-belt) EV, battery, automotive, charging, or clean-energy supply chain: companies, joint ventures, facilities/plants/sites, investments and incentives, jobs/hiring/layoffs, workforce training, products and components, capacity and output, customers and suppliers, partnerships, government programs and policy, people and officials, events, timelines, and any quantitative or qualitative detail tied to these.

COVERAGE CHECKLIST - scan the page for each and write a fact for every instance you find:
- Money: investment amounts, incentives/grants/tax values, costs, funding (keep exact figures and qualifiers like "up to", "over", "combined").
- Quantities & capacity: GWh, tons/tonnes per year, square footage, number of plants/lines, acreage, production volumes, vehicle-per-year equivalents.
- Jobs: hiring goals, current headcount, layoffs, roles/areas, timelines, wages/benefits.
- Dates & timeline: every dated or time-qualified event (announced, groundbreaking, start of production, milestones, layoffs, investigations); keep approximate timing approximate.
- Places: site addresses, city, county, state, industrial parks, corridors.
- Organizations: parent/subsidiary, JV partners, customers, suppliers, technology providers, agencies, authorities, chambers, utilities, colleges, staffing firms — name the relationship.
- People: executives, governors, mayors, commissioners, project managers, officials, spokespeople — with their role/title.
- Products/technology: cell chemistries, components, applications, end markets, customer vehicle models.
- Status: announced / under construction / operational, plus expansions, delays, closures.
- Context & significance: state totals, rankings (e.g. "e-mobility capital"), regulatory findings, and notable direct quotes (quote them).

HOW TO WRITE EACH FACT:
- One self-contained statement per bullet, understandable on its own.
- Preserve names, dates, amounts, quantities, places, and qualifiers EXACTLY as stated on the page.
- Attribute quotes and claims to who said them when the page says so.
- Do not merge several distinct facts into one bullet; do not split one fact so it loses meaning.

LINKS AND CALLS-TO-ACTION (strict):
Never leave a raw URL, web address, email, phone number, or "visit/apply/see X for more information" call-to-action inside the facts list. Instead:
- If a sentence contains BOTH a real fact AND a link/CTA: keep the fact in "facts" with the URL removed from the text, and record the URL in the separate "links" list with a short context. Example: source "The company is still hiring for production, quality, logistics and maintenance roles. Career information can be found at www.example.com." -> facts: "Is still hiring for production, quality, logistics and maintenance roles."; links: {"url": "www.example.com", "context": "Careers page"}.
- If a sentence is ONLY a link/contact/CTA with no standalone fact: omit it from "facts" entirely (you may still record the URL in "links").
- The "facts" strings must contain no URLs, email addresses, or phone numbers.

Rules:
- Return valid JSON only, matching the schema below.
- Create ONE record for the page's primary entity. Add another record only if the page is equally and primarily about a second distinct entity; otherwise keep everything (including facts about partners, customers, and people) in the primary record's facts list.
- Set canonical_name to the entity's full official name, entity_type to one of the allowed values, and supply_chain_category to one of the allowed values (best fit).
- If the page has NO content relevant to the Georgia EV / battery / automotive / charging / workforce / supply-chain project, return {"records": []}.
- Leave source_url, source_title, source_domain empty; the pipeline stamps them after generation.

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
      "supply_chain_category": "",
      "facts": [
        "First project-relevant fact, verbatim numbers and qualifiers (no URLs).",
        "Second fact ..."
      ],
      "links": [
        {"url": "", "context": ""}
      ],
      "source_url": "",
      "source_title": "",
      "source_domain": ""
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

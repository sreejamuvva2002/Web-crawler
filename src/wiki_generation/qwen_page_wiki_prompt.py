"""The spec's page-level Qwen prompt. The rules are verbatim; the return-format
section is adapted from a bare JSON array to an object with a "records" array,
matching PageRecordsResponse (an object root is required for JSON mode and vLLM
guided decoding)."""

PAGE_WIKI_PROMPT_TEMPLATE = """You are creating a source-backed LLM Wiki for the Georgia electric vehicle supply-chain domain.

Use only the provided Crawl4AI page content.

Your task is to extract structured wiki records about companies, facilities, investments, products, services, suppliers, battery materials, EV components, charging infrastructure, workforce programs, government programs, and relevant Georgia EV supply-chain activity.

Rules:
1. Use only the provided page content.
2. Do not use outside knowledge.
3. Do not guess missing values.
4. Every record must include source_url.
5. Every record must include evidence_text.
6. If the page has no Georgia EV supply-chain relevance, return an empty records array.
7. Return valid JSON only.
8. Do not include explanation outside JSON.
9. Keep each record specific and evidence-backed.
10. Do not merge facts from different pages in this step.

Source URL:
{source_url}

Source title:
{source_title}

Source domain:
{source_domain}

Crawl4AI Markdown content:
{page_markdown}

Return a JSON object with a "records" array using this schema:
{
  "records": [
    {
      "entity_type": "",
      "entity_name": "",
      "canonical_name": "",
      "summary": "",
      "location": "",
      "county": "",
      "state": "Georgia",
      "country": "United States",
      "ev_relevance": "",
      "supply_chain_category": "",
      "products_or_services": [],
      "customers_or_oems": [],
      "investment_amount": "",
      "jobs": "",
      "facility_status": "",
      "dates_mentioned": [],
      "source_url": "",
      "source_title": "",
      "source_domain": "",
      "evidence_text": "",
      "confidence_score": 0.0,
      "notes": ""
    }
  ]
}"""


def build_prompt(page_input: dict) -> str:
    # .replace, not .format — the schema block's braces would break format()
    return (
        PAGE_WIKI_PROMPT_TEMPLATE.replace("{source_url}", page_input.get("source_url", ""))
        .replace("{source_title}", page_input.get("source_title", ""))
        .replace("{source_domain}", page_input.get("source_domain", ""))
        .replace("{page_markdown}", page_input.get("page_markdown", ""))
    )

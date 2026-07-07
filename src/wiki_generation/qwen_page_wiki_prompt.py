"""Stage 5's page-level prompt. One primary entity per page, with everyone else
mentioned folded into related_organizations/workforce_programs on that one
record instead of becoming records of their own. Matches PageRecordsResponse
(an object root is required for JSON mode and vLLM guided decoding).

entity_types/supply_chain_categories come from configs/wiki_schema.yaml (the
same vocabulary the validation stage enforces) so the prompt can never drift
out of sync with what's actually allowed."""

"""Stage 5's page-level prompt — v7.1.
 
Surgical revision of v7. Only the rules tied to confirmed extraction failures
were changed; everything else is byte-identical to v7 so diffs stay small.
 
Changed vs v7:
  - Rule 6  : relevance gate hardened into a hard FIRST filter + reject-list
              (fixes off-domain false positives: Bojangles, hotels, golf-cart
              dealers, chamber-of-commerce "electric motor repair" listings...)
  - Rule 19 : claim_status now explicitly EMPTY for non-project entities
              (fixes GAMA trade association tagged "operational")
  - Rule 21 : publisher/wire/syndicator exclusion reinforced
              (fixes Atlanta Journal-Constitution + Tribune Content Agency in
              related_organizations on the tax-credit page)
  - Rule 26 : hard ceiling — 1.0 forbidden; score must vary by page quality
              (fixes the 95.7%-are-1.0 problem in the flat sample)
  - Rule 29 : context-scope on policy pages made mandatory
              (fixes Rivian/Hyundai tagged "entity" and IRA tagged
              "company_wide" on the tax-credit page)
  - Rule 30 : relationship grounding + no per-customer product splitting
              (fixes LG "former owner" and Mobis HMMA/Kia product split)
  - NEW     : a PRE-OUTPUT SELF-CHECK block before the Source fields.
 
NOT changed here (fix in the pipeline, not the prompt):
  - publication_date: parse deterministically from the URL slug / dateline in
    code and pass it in via {publication_date}; do not rely on the model. This
    removes the run-to-run flip (a page had a pub date on 07-06 and lost it on
    07-07).
  - boilerplate stripping (Crawl4AI fit_markdown / trafilatura) and a crawl-time
    junk/404/index-page gate belong upstream of this prompt.
"""
 
PAGE_WIKI_PROMPT_TEMPLATE = """You are creating a source-backed LLM Wiki for the Georgia electric vehicle supply-chain domain.
 
Use only the provided Crawl4AI page content.
 
This page is a single source document. Identify the ONE primary entity this page is centrally about — usually a company, facility, project, government program, research center, charging-infrastructure initiative, policy/incentive, joint venture, or event. Produce ONE wiki record for that primary entity. Only produce a second record if the page is genuinely and equally about two separate primary subjects (rare).
 
Every other organization, agency, program, or person mentioned only in relation to the primary entity — parent/subsidiary companies, OEM customers, workforce-training partners, contractors, government agencies, oversight bodies, chambers of commerce, and named people — belongs in related_organizations or workforce_programs on the primary entity's record. Do NOT create a separate top-level record for them; they may get their own dedicated record later from a different source page that is actually about them.
 
COMPLETENESS IS CRITICAL. Before you write your final answer, scan the page a second time and make a mental list of every proper noun: every named organization, agency, company, program, and person, including ones mentioned only once, only in passing, or only as "a partner of X" / "which oversees Y". Every single one of them must appear somewhere in the output — in related_organizations, workforce_programs, or facilities — even minor ones. Do not stop after capturing the first few most prominent names. Likewise, if the page states a count (e.g. "two facilities", "three plants"), the facilities list must reflect that count, one entry per facility, not one combined entry. And the timeline list must include every dated event on the page, including background/history dates (e.g. when a site was zoned), not just the headline announcement date.
 
NARRATIVE FACTS MATTER TOO, not just named entities. Scan the page a third time specifically for descriptive activity/outcome statements that have no proper noun attached — e.g. "held numerous career fairs, visited schools, and held community events", "consistently improved wages, benefits, and its overall work environment", production milestones, safety/quality claims, sustainability commitments, or any other concrete claim about what the entity did or achieved. Put each such statement in key_facts even when it names no other organization or person. Do not drop a fact just because it lacks a proper noun — only drop it if it is pure filler with no concrete content.
 
BROADER CONTEXT QUOTES MATTER TOO. Government press releases often include an official's quote or a closing paragraph about the state/region/industry ecosystem surrounding the primary entity's announcement — e.g. a state economic-development official describing why the state is developing "a battery ecosystem with manufacturers, recyclers, and customers", or a paragraph about the state's infrastructure, workforce, business climate, or supply-chain strategy. These are substantive claims made specifically in connection with the primary entity's project, even though they are about the surrounding ecosystem rather than the entity itself — capture them in key_facts too. Only skip pure boilerplate (e.g. generic mission-statement filler with no specific claim).
 
Rules:
1. Use only the provided page content.
2. Do not use outside knowledge.
3. Do not guess missing values.
4. Every record must include source_url.
5. Every record must include evidence_text — a real quote or close paraphrase from the page supporting the primary entity's Georgia EV supply-chain relevance.
6. RELEVANCE GATE — apply this FIRST, as a hard filter, before extracting anything. Produce a record ONLY if the page's PRIMARY subject has a DIRECT, MATERIAL role in Georgia's electric-vehicle supply chain — i.e. it makes, assembles, supplies, powers, recycles, finances, sites, regulates, or trains the workforce for EVs, EV batteries, EV components, or EV charging IN GEORGIA. The test is concrete: you must be able to quote ONE sentence from the page tying the primary entity to the Georgia EV / battery / charging supply chain. If you cannot, return an empty records array and nothing else — do NOT lower the bar to fill the output. Return EMPTY even when the words "electric", "motor", "battery", "charging", or "Georgia" appear, if the page is really about any of: a general local business (restaurant, hotel, apartment community, shopping center, golf-cart dealer, car dealership or service center, law firm); a directory or business-listing page (e.g. a chamber-of-commerce listing, "electric motor repair" or industrial-motor shops with no EV tie); an airport, port, or venue named only as a location; or a lifestyle/science/news article that merely mentions EVs in passing. When in doubt about relevance, emit no record rather than a weak one.
7. Return valid JSON only.
8. Do not include explanation outside JSON.
9. Keep every fact specific and evidence-backed — do not invent dates, amounts, or names not present on the page.
10. Do not merge facts from different pages in this step — this record covers only this one page.
11. entity_type must be exactly one of: {entity_types}. Choose the closest fit. Copy the value VERBATIM from that list — do not change its casing, spelling, or wording, and never invent a new type.
12. supply_chain_category must be exactly one of: {supply_chain_categories}. Use "unknown" only if none fit. Copy the value VERBATIM — do not change casing, spelling, or wording, and never invent a new category.
13. facilities, investment, jobs, workforce_programs, related_organizations, timeline, and key_facts are all optional lists — leave a list empty if the page has nothing for that section. Do not pad them with guesses, but do not skip real named entities either — see the completeness note above.
14. For each related_organizations entry, give a short "role" describing its relationship to the primary entity (e.g. "Parent company", "Automaker customer", "Workforce training partner", "Government agency", "Oversight body", "Contractor", "CEO", "State official"). Include every named person on the page this way too, even the primary entity's own executives.
15. title should be a short page title: the entity name alone, or "Entity Name — Project/Facility Name, County, Georgia" when the page centers on a specific named project or facility.
16. overview must be a full connective narrative paragraph (aim for 4-6 sentences), not a short summary. The structured lists below (facilities, investment, jobs, etc.) intentionally break facts into separate items, which loses the *relationships between* those facts — the overview is where that connective meaning belongs. Explicitly weave together: what the entity is and does, what project/facility/announcement this page covers, why it matters (its purpose, technology, or role in the supply chain), and which key partners or programs are involved and how — the same way a human-written company profile would connect these ideas into one coherent narrative, not a bulleted recap of the structured sections.
17. Put in "details" only facts that genuinely do not fit any structured section above (e.g. certifications, website/contact info — if the page gives a website or careers URL, always include it here). Leave it empty if there is nothing left over.
18. RESOLVE RELATIVE TIME to absolute dates using the Source publication date above as the anchor, but ONLY TO THE PRECISION THE SOURCE ACTUALLY SUPPORTS. Convert "next year"/"by next year" to the year (e.g. from a 2023 page -> "2024"); "over the next seven years" anchored to a 2022 page -> "by 2029". Do NOT fabricate a month or day the source did not state: "end of 2022" becomes "2022" (NOT "2022-12-31"), "mid-2023" becomes "2023", "this quarter" becomes the quarter's year. Use a full YYYY-MM-DD only when the source gives an actual full date. It is fine to keep a qualifier in the event text (e.g. date "2022", event "Met hiring goal by end of 2022"). If — and only if — no publication date is provided above, keep the original wording and do NOT guess a year.
19. claim_status describes the status of a PHYSICAL PROJECT OR FACILITY only, chosen from exactly: announced, under_construction, operational. Use the page's own language: "will build" / "plans to" / "announced" -> announced; "is building" / "under construction" / "breaking ground" -> under_construction; "began production" / "now operating" / "opened" -> operational. NEVER output cancelled or superseded — a single announcement page cannot know a project was later scrapped; that is decided later from other sources. Leave claim_status EMPTY for any entity that is NOT a buildable project or facility: this includes trade associations, chambers of commerce, government agencies, universities, workforce programs, policies/incentives, people, products, and vehicle models. An organization that merely "exists and operates" is NOT "operational" in this field — operational/under_construction/announced apply to plants, sites, and construction projects, not to organizations, programs, or policies. For a POLICY / INCENTIVE / NEWS-ANALYSIS page, leave claim_status EMPTY.
20. SEPARATE COMPANY-WIDE FACTS FROM THIS GEORGIA ENTITY/PROJECT — but DO NOT DROP THEM. Global or corporate boilerplate figures — a parent company's worldwide capacity roadmap, global revenue targets, total employees across all countries, "About [Company]" section goals (e.g. "aims to install 50 GWh by 2025, 100 GWh by 2028, 200 GWh by 2030 globally") — are NOT this Georgia facility's own numbers, but they are still real facts from the page and must be KEPT. Put each such dated global target in the timeline (or investment) with "scope": "company_wide" so it is preserved without being confused for the Georgia facility's roadmap. Facts specifically about the Georgia entity, facility, project, its Georgia investment, or its Georgia jobs get "scope": "entity" (the default). When unsure, prefer "entity" only if the fact is clearly tied to the Georgia project.
21. related_organizations must contain ONLY real entities named in the article body with a genuine OPERATIONAL / project / workforce / technology / customer / government / supply-chain relationship to the primary entity (parent/subsidiary, customer/OEM, workforce or technology partner, contractor, supplier, government agency, oversight body, named executive/official). Do NOT extract entities from navigational chrome — "Related Links", "Related Articles", "More News", "Read More", sidebars, breadcrumb menus, or press/media-contact blocks. Do NOT include a stock exchange the entity is merely listed on (e.g. "listed on the New York Stock Exchange"), an index, a passing "not affiliated with" mention, or any name with no real relationship — a stock listing belongs in "details", not related_organizations. Do NOT include PRESS or COMMUNICATIONS CONTACTS (e.g. a press secretary, deputy press secretary, communications manager, media-relations person, or spokesperson listed in a "Press Contacts"/"Media Contacts"/"Contact" block) — they are contacts, not project partners. Do NOT include bare GEOGRAPHIC LOCATIONS (a city, state, or "existing footprint" location such as "Niagara Falls, New York") — a place is not an organization; company-background/footprint locations belong in "details", and the entity's own headquarters belongs in the "headquarters" field. Do NOT include the PUBLISHER, NEWSPAPER, WIRE SERVICE, or CONTENT/SYNDICATION AGENCY that produced or distributed the article itself — this holds even when the outlet looks like an ordinary organization and is named in the article body or byline (e.g. "Atlanta Journal-Constitution", "Tribune Content Agency", "Associated Press", "PR Newswire"): the outlet that wrote, published, or syndicated THIS story is source metadata, never a related_organization. Before adding any media / news / wire / PR entity, confirm it has an operational relationship to the primary entity OTHER than reporting on it; if its only role is producing or distributing the article, omit it entirely. If you are unsure whether a name came from the article body or from a related-link list, set its "source" to "related_link"; otherwise set "source" to "body". Never invent a relationship for a name that only appeared in a related-link title.
22. FACILITIES: do not invent distinct facility names. If the page says there are N facilities ("two lithium-ion battery plants") but does NOT name them individually, emit ONE facilities entry describing them collectively with "count" set to N (e.g. name "Commerce Battery Manufacturing Facilities", count "2"), not N entries with fabricated names like "Facility 1"/"Facility 2". Only create separate entries when the page actually names them separately. Fill each facility's "capacity" and "status" from anywhere on the page even if stated in a different sentence — e.g. a combined "22 GWh per year, enough for ~300,000 EVs" becomes capacity "22 GWh per year combined", and mass-production language makes status "operational".
23. LOCATION vs HEADQUARTERS — this is important. The top-level "location"/"county"/"state" must describe the GEORGIA project/facility this page is about — the place where the investment, jobs, and facility are (e.g. "Bainbridge, Georgia" / "Decatur County"). It must NOT be the company's corporate headquarters. If the page's "About" section gives a different headquarters city (e.g. "Anovion is headquartered in Chicago, Illinois"), put that in the separate "headquarters" field and keep it OUT of location/county. location should be as specific as the page supports and include the county and state when known (prefer "Bridgeport Industrial Park, Coweta County, Georgia" over just "Bridgeport Industrial Park"); keep "county" as the county alone (e.g. "Coweta County").
24. WORKFORCE PROGRAMS: any named workforce-development, job-training, or recruiting program that appears as a project partner (e.g. "Georgia Quick Start", "Work for Warriors") must be listed in workforce_programs with a "relationship", even when it is also mentioned among the project's partners. Do not leave workforce_programs empty when such a program is named on the page. (It is fine for the parent agency, e.g. the Technical College System of Georgia, to also appear in related_organizations.)
25. evidence_snippets: in addition to the single primary evidence_text, provide a short list of real quotes/close paraphrases from the page that separately support the main facets you extracted — location, investment amount, jobs/hiring, capacity, key partners, workforce programs, and status — so each major claim has its own grounded snippet. Keep each snippet short and copied/closely paraphrased from the page. Leave the list empty only if the page is too thin to support more than the primary evidence_text.
26. confidence_score reflects how well the page supports your extraction, and MUST vary by page quality. NEVER output 1.0 — 1.0 is reserved and forbidden. Use 0.90-0.95 for a clean, fully unambiguous press release; drop to 0.70-0.85 when the page is thin, undated, republished/syndicated, or required any inference; use below 0.5 when relevance or key facts are uncertain. A page that only barely passes the Rule 6 relevance gate must score below 0.6. Do not emit the same score for every record.
27. PRESERVE EXACT FIGURES AND THEIR QUALIFIERS everywhere (amounts, overview, key_facts, investment). Do not round or drop qualifier words: "over $800 million" stays "over $800 million" (not "$800 million"); "more than $21.9 billion" stays "more than $21.9 billion" (not "$21 billion" or "$21.9 billion" without the "more than"); keep "approximately", "up to", "nearly", "at least", and decimals exactly as the page states them.
28. DO NOT LEAVE timeline.date BLANK when the page gives the date. Use the article dateline (e.g. a "CITY — May 15, 2023" dateline, or the Source publication date above) as the date of the announcement event, and date every other event to the precision the page supports ("late 2025", "2025", "Q3 2025"). Only leave a timeline date blank if the page genuinely attaches no date to that event.
29. CONTEXT / BACKGROUND FACTS ABOUT OTHER ENTITIES — common on policy, incentive, and news-analysis pages. On such a page the primary entity is the POLICY or TOPIC itself, and EVERY other company, project, or law mentioned as background MUST be tagged "scope": "context" — this includes federal laws such as the Inflation Reduction Act, and other companies' Georgia projects (e.g. "Rivian announced a Georgia factory in 2021", "Hyundai is building a Metaplant outside Savannah"). Do NOT tag these "entity" (that is only for the policy/topic's own facts) and do NOT tag them "company_wide" (that is ONLY for the primary entity's own global roadmap; a policy has none, so "company_wide" should not appear at all on a policy page). Still capture every such fact; just mark it "context" so it is not mistaken for the primary subject's own fact.
30. DESCRIBE EACH RELATIONSHIP EXACTLY AS THE SOURCE STATES IT — never infer ownership, operation, employment, purchase, or history the page does not state. Every "role" you write for a related_organization, and every customer relationship, MUST be directly supported by a specific sentence on the page; before finalizing, re-check each role string against the text. NEVER upgrade a party's role to a stronger claim: if the page only says parties reached a "settlement" (e.g. "a settlement between SK Innovation and LG saved the Commerce battery plant"), you may state ONLY that they were parties to that settlement — it is FORBIDDEN to call either party the "owner", "former owner", "operator", "former operator", or "buyer" of the plant, because the page never says so. Likewise do not infer that a mentioned company is a "supplier", "customer", or "partner" unless the page says so. AND when a facility supplies MULTIPLE named customers with a COMBINED output (e.g. "will supply over 900,000 EV power systems and 450,000 charging units annually to A, B, and C"), do NOT split specific products among specific customers — record that it supplies all listed customers with the stated combined output. Assigning product X to customer A and product Y to customer B when the page states a joint total is a fabricated relationship. When unsure of the precise relationship, use the page's own wording or a vaguer role — a vaguer role is acceptable, a stronger-than-stated role is a factual error and is not.
31. KEEP APPROXIMATE TIMING AS APPROXIMATE — do not over-normalize. When the source gives approximate timing, preserve the qualifier in the event text ("since 2019", "end of 2022", "late 2025", "by 2029") and set the date field only to the precision the source supports (year, or blank). Never convert an approximate phrase into a fabricated exact date. Missing a date or two is acceptable; a fabricated wrong date is not.
 
PRE-OUTPUT SELF-CHECK — run this on your draft before you emit JSON, and fix any failure:
(a) RELEVANCE (Rule 6): Can you quote ONE sentence tying the primary entity to the Georgia EV / battery / charging supply chain? If no -> return an empty records array and stop.
(b) PUBLISHER / CONTACTS (Rule 21): Does related_organizations contain any news outlet, wire service, PR service, or press/media contact whose only role is producing or distributing this article? If yes -> remove it.
(c) ROLE GROUNDING (Rule 30): Is every related_organizations "role" and every customer relationship backed by a specific sentence on the page? Any "owner"/"former owner"/"operator"/"buyer"/"supplier"/"customer" not stated in the text -> downgrade to exactly what the page says. Any per-customer product split against a combined total -> collapse to the combined output for all customers.
(d) CLAIM_STATUS (Rule 19): Is the primary entity a physical project or facility? If it is an association, agency, university, program, policy, person, product, or vehicle model -> claim_status must be empty.
(e) SCOPE (Rules 20 & 29): On a policy/news page, is every OTHER entity's timeline/investment tagged "context"? Any stray "entity" or "company_wide" -> fix. On a project page, are global/corporate roadmap figures tagged "company_wide" and Georgia-specific facts "entity"?
(f) CONFIDENCE (Rule 26): Is confidence_score strictly less than 1.0 and does it reflect THIS page's actual quality (thin/undated/syndicated -> lower)?
(g) VOCAB (Rules 11 & 12): Are entity_type and supply_chain_category copied verbatim from the allowed lists, with no casing or spelling changes and nothing invented?
 
Source URL:
{source_url}
 
Source title:
{source_title}
 
Source domain:
{source_domain}
 
Source publication date (the date this page was published; use as the anchor for resolving relative time expressions):
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
    # .replace, not .format — the schema block's braces would break format()
    schema = settings.wiki_schema
    entity_types = ", ".join(schema.get("entity_types", []))
    supply_chain_categories = ", ".join(schema.get("supply_chain_categories", []))
    publication_date = (page_input.get("publication_date") or "").strip() or "(unknown — do not guess a year)"
    return (
        PAGE_WIKI_PROMPT_TEMPLATE.replace("{entity_types}", entity_types)
        .replace("{supply_chain_categories}", supply_chain_categories)
        .replace("{source_url}", page_input.get("source_url", ""))
        .replace("{source_title}", page_input.get("source_title", ""))
        .replace("{source_domain}", page_input.get("source_domain", ""))
        .replace("{publication_date}", publication_date)
        .replace("{page_markdown}", page_input.get("page_markdown", ""))
    )
 
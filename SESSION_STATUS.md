# Pipeline status handoff (updated 2026-07-07 ~00:50 UTC)

If this chat is lost: paste the exported transcript into a new Claude session, or just point a
fresh Claude at this file — everything here is derived from files on disk and can be re-verified
directly, no chat memory required.

## What's running right now (background, survives SSH/VPN disconnect via nohup+disown)

1. **Discovery** — `python -m src.discovery.collect_urls --provider ddgs`, PID 3841210 (still the
   same process). Network/CPU only, no GPU dependency.

2. **Stage 4 crawl loop** — `scripts/crawl_until_done.sh` (relaunched this session; wrapper PID
   352485, active python crawl PID 352503), log `logs/crawl_urls_run.log`. Crawls the frontier
   `queued` backlog in batches of 1,000 (the config's `max_urls_to_crawl` cap), looping until either
   no `queued` rows remain or free disk drops below 3GB. **Still running — this is the thing we are
   waiting on** before doing anything with Stage 6 (per explicit user instruction: "wait for
   crawling to finish, then run Stage 6"). Frontier at last check (~20:00 UTC): `queued` 9,510 /
   `crawled` 7,403 / `failed` 2,602 / `rejected` 1,975 / `needs_review` 614. **Disk is tight — 20 GB
   free, `/` at 100%.** The loop self-stops if free disk drops below 3 GB.

**Stage 5 full wiki generation is DONE** (the process finished on its own and is no longer running
— do not expect to see a PID for it). Results below.

## Bugs found + fixed this session
1. **Wrong model on restart**: Stage 5 background jobs were found running against `qwen3:235b`
   (from `.env`'s committed default) instead of the validated `gpt-oss:120b`. Killed and relaunched
   correctly with `QWEN_MODEL=gpt-oss:120b`. **Always verify `ollama ps` shows `gpt-oss:120b` after
   any restart**, not `qwen3:235b`.
2. **`crawl_with_crawl4ai.py --limit` bug**: passing a higher `--limit` than
   `configs/crawler_config.yaml`'s `max_urls_to_crawl: 1000` silently does nothing — the code does
   `min(args.limit or settings.max_urls_to_crawl, settings.max_urls_to_crawl)`, which always clamps
   to the config value. Worked around via the looping wrapper script (`scripts/crawl_until_done.sh`)
   rather than fixed in place — still a real bug in that file, not fixed.
3. **Entity-merge clustering was name-only** (`group_records_by_entity.py`): it fuzzy-matched purely
   on normalized entity name, with no awareness of `entity_type` or location. Risk: a parent company
   and its own facility (or an unrelated same-named company) can share most name tokens and get
   wrongly merged. **Fixed** — see "What changed" below.

## Stage 5 results (full 823-page run, DONE)
- 823/823 pages processed, 644 raw records, **zero generation failures**
  (`data/wiki/wiki_records_raw.jsonl`, `data/wiki/pages_processed.jsonl`).
- All `entity_type` values landed on valid enum members (company 435, facility 107,
  government_program 32, joint_venture 23, research_center 12, charging_infrastructure 8,
  policy_or_incentive 7, investment_announcement 7, workforce_training 5, person 4, event 4) — a
  complete turnaround from the old broken-schema run's 100% failure.
- Ran `python -m src.wiki_generation.validate_page_records` (Stage 5 validation: schema checks +
  source-grounding fuzzy-match against the page markdown + duplicate-fact removal) for real:
  **480/644 pass → `data/wiki/wiki_records_validated.jsonl`**, 164 fail →
  `data/wiki/wiki_records_failed.jsonl` (mix of not_georgia_related / not_ev_related / too_generic /
  unsupported_claim rejections — spot-checked several, all legitimate, e.g. Toyota/VinFast plants in
  North Carolina correctly rejected as not-Georgia).
- Ran `python -m src.wiki_generation.group_records_by_entity` for real (deterministic, no LLM call):
  **480 validated records → 229 entity groups, 58 with >1 record, 34 flagged needs_review**.
  Spot-checked the needs_review list — it correctly caught a cluster of near-duplicate
  Hyundai/SK-On facility and joint-venture name variants (e.g. "Hyundai Motor Group & SK On Battery
  Plant" vs "...Battery Manufacturing Facility" vs "...EV Battery Facility", all in Bartow County)
  that plausibly refer to the same thing but weren't confident enough to auto-merge — exactly the
  "same name, could be same or different entity" case that needs the Stage 6 LLM merge's full
  context to resolve, not silent guessing either way.

## What changed this session (beyond the earlier schema/prompt rewrite + narrative-fact fixes)
User raised a design question: does decomposing pages into structured JSON fields lose the
*meaning*/*connective narrative* of a source page, and is name-only entity merging risky? Both
concerns were valid; concrete fixes made (both re-tested against real gpt-oss:120b inference and
the real 823-page corpus, not just unit tests):

1. **`src/wiki_generation/group_records_by_entity.py` — entity-type-aware clustering.**
   Records are now partitioned by `entity_type` before any name-fuzzy-matching happens, so a
   company can never auto-merge with its own facility or an unrelated same-named entity of a
   different type. Within a type, if two similarly-named records both carry a location
   (`county`/`location`) and those locations clearly disagree (compared after stripping filler words
   like "County"/"Georgia" — see `_normalize_location`), a would-be auto-merge is downgraded to
   `needs_review` instead. New tests in `tests/test_entity_grouping.py`
   (`test_conflicting_locations_downgrade_to_review_not_automerge`,
   `test_matching_or_missing_locations_still_automerge`). `cluster_names()`'s signature grew an
   optional `location_of` param (backward compatible, defaults to `None`).

2. **`overview` field strengthened** in both `src/wiki_generation/qwen_page_wiki_prompt.py` (Stage 5,
   new rule 16) and `src/wiki_generation/qwen_entity_merge_prompt.py` (Stage 6, rule 9): instead of
   "a short paragraph," it now explicitly asks for a full connective narrative (4-6 sentences at
   Stage 5, 5-8 at Stage 6) that weaves together what the entity does, what the page's
   announcement/project is, why it matters, and which partners/programs are involved and how — the
   idea being that the structured lists (facilities/investment/jobs/etc.) intentionally decompose
   facts into parallel items, so the *relationships between* those facts need to live somewhere, and
   `overview` is that place. Re-tested on `page_000001`/`page_000002` against gpt-oss:120b: overviews
   are now noticeably richer (e.g. FREYR's overview now explicitly connects the project to "a
   coordinated effort to grow Georgia's sustainable technology ecosystem" backed by the named
   partners, not just a flat fact list) while still passing validation + grounding cleanly.

Tests: `python -m pytest tests/` → **29/29 passing** (was 27, +2 new).

Saved a fourth round of test samples (post-overview-strengthening) at
`data/wiki/_prompt_test_samples_20260706_v4/` (page_000001/page_000002 raw records only — `_v3`
before it already covers the merged-profile shape and is still valid/kept).

**Important**: `data/wiki/wiki_records_validated.jsonl` and `data/wiki/entity_groups.jsonl` were
regenerated for real against the full 644-record corpus to test the clustering fix above — both are
deterministic, non-LLM steps, so this didn't violate "wait for crawling before Stage 6." **The
actual Stage 6 LLM merge (`generate_entity_wiki.py`, which calls the LLM once per entity group) has
NOT been run on the full corpus** — still correctly waiting on the crawl loop to finish, per
explicit instruction.

## Chat 4 audit batch — DONE and verified (2026-07-06 ~20:05 UTC)
Continuation of the Chat 4 session, which hit its usage limit mid-verification. That session was
working through a 7-point audit of the Stage 5 record for the **Anovion Technologies** georgia.org
press release (`page_000005`, `https://georgia.org/press-release/anovion-technologies-create-over-400-jobs-bainbridge-invest-800m-manufacturing`).
Tasks 12–14 (the fixes) were implemented but not yet verified when the limit hit. **Now complete and
verified end-to-end.** No new code changes were needed this continuation — only verification.

The 7 audit fixes and how each was confirmed:
1. **HQ overriding the Georgia project location** → new `headquarters` field + `_relocate_to_georgia_project`
   safety net in `validate_wiki_records.py`. Live inference now yields `location: "Downrange Industrial
   Park, Bainbridge"`, `county: "Decatur County"`, `headquarters: "Chicago, Illinois"` (was `location:
   Chicago, IL`).
2. **Body-dateline publication date** → new `src/crawling/publication_date.py` (`date_from_text`,
   priority chain `html_meta → body_dateline → url_path → none`), wired into `build_page_inputs.py`
   (line ~115 fallback). Live output: `publication_date: 2023-05-15`, `date_precision: body_dateline`,
   `currency: stale`.
3. **Figure qualifiers (rule 27)** — "over $800 million" preserved in `investment.amount` AND
   `overview` (was "$800 million").
4. **Press contacts leaking into related_organizations** → `clean_related_organizations` + press-role
   markers in `validate_wiki_records.py`. Carter Chapman / Annalise Morning / Jessica Atwell gone.
5. **Footprint cities (Niagara Falls / Clarksburg) leaking** → same cleanup (footprint marker). Gone.
6. **Blank timeline dates (rule 28)** — all 3 timeline events dated on live output (`2023-05-15`,
   `late 2025`, `early 2021`).
7. **Overview figures** — same rule 27; overview uses "over $800 million".

Verification performed this continuation:
- `python -m pytest tests/` → **52/52 passing** (was 47 earlier in the Chat 4 session; +5).
- Behavioral repro of the exact Anovion failure shape against `_relocate_to_georgia_project` +
  `clean_related_organizations` (deterministic, no LLM) — all pass.
- `publication_date.py` behavioral check across all signals — correct.
- **One real single-page inference run** against `gpt-oss:120b` on `page_000005` (the pattern the Chat
  4 session used), replayed in an isolated scratchpad script that wrote ONLY to scratchpad — the
  corpus jsonl files were NOT touched. Confirmed rules 27/28 + all deterministic fixes on live output.
  **The demo record is saved in-repo at `data/wiki/_prompt_test_samples_20260706_v7/page_000005_anovion_v7.json`**
  (+ a README comparing it field-by-field to the stale on-disk corpus record). **Reminder: `.env` still has the wrong
  `QWEN_MODEL=qwen3:235b` default — the run was pinned with `QWEN_MODEL=gpt-oss:120b` on the CLI.
  Always override.**

Two minor, non-blocking observations from the live output (neither a regression):
- `related_organizations` now mixes named officials/executives (Gov. Kemp, Pat Wilson, Eric Stopka) with
  orgs — per-spec (rule 21 allows named officials), and exactly the still-open "People Mentioned vs
  Related Organizations" split question below.
- One `investment` entry has a blank amount tied to `early 2021` (the "began commercial production"
  milestone mildly over-captured as an investment; also correctly in the timeline). Cosmetic.

**Still uncommitted** — this batch lives in the working tree only, same as the rest of the session.

## Chat 5 audit batch — DONE and verified (2026-07-07)
A second audit (Chat 5) reviewed live-inference samples for pages 1/2/5/6/9/10/12/13/14 and found
the format strong for company/facility pages (Ascend Elements, Hyundai Mobis, FREYR, SK Battery,
Anovion all good) but flagged 7 fixes needed before the full Stage 5 run — mostly around
policy/news pages, body-date extraction, and duplicate reposts. **All 7 addressed and verified.**

Root cause found for the missing dates: visible body dates (`Published">June 05, 2025`,
`<time>May 20, 2022</time>`) live in the raw HTML but are (a) not in `<head>` meta, (b) stripped
from the trafilatura markdown, and (c) past the first 2000 chars that `date_from_text` scans — so
every date path missed them. crawl_metadata.csv also has NO publication_date column (live-crawl
constraint), so dates only reached Stage 5 via the 15-row backfill sidecar.

The 7 fixes and how each was confirmed (live `gpt-oss:120b` on pages 9=policy, 10=Ossoff):
1. **Body-labeled dates** → new `date_from_labeled_html` in `publication_date.py` (Published/Posted
   labels + bare `<time>` text, whole-HTML scan) + raw-HTML fallback in `build_page_inputs.py`.
   Page 9 → `2025-06-05`, page 10 → `2022-05-20` (both were `""`).
2. **URL year/month** → `date_from_url_month` + new `url_path_month` precision (`/2022/11/` → `2022-11`).
3. **Timeline/investment `scope: "context"`** for background events about OTHER entities on
   policy/news pages (schema doc + prompt rule 29). Live output uses it (SK/LG settlement, IRA sunset).
4. **Publisher/distributor cleanup** → `_PUBLISHER_MARKERS` in `clean_related_organizations`
   (drops "Atlanta Journal-Constitution" / "Tribune Content Agency"). Gone from page 9.
5. **Invented LG relationship** → prompt rule 30 (relationship accuracy). "Former owner/operator of
   the plant" → "Company whose … settlement was facilitated by Ossoff" — no longer over-claims.
6. **Repost dedup** → confirmed the EXISTING Stage 6 grouping already merges reposts by
   name+type+location (never source URL); Hyundai Mobis page_000013+014 cluster into one entity,
   both sources retained. No code change needed; locked with a regression test.
7. **Policy `claim_status`** → prompt rule 19 says leave blank for policy_or_incentive/news pages
   (blank already schema-valid). Page 9 → `claim_status: ""`.
   Plus approximate-date phrasing (rule 31): "November (unspecified)" → `November 2021`.

Verification: **59/59 tests pass** (+7 new). Post-fix samples saved in-repo at
`data/wiki/_prompt_test_samples_20260707_v8/` (page 9 + 10, with a README comparing to v7).
Isolated harness, corpus jsonl untouched. **`.env` still defaults to the wrong `qwen3:235b` —
always override with `QWEN_MODEL=gpt-oss:120b`.**

**Did NOT touch `CRAWL_METADATA_COLUMNS`** (crawl is live; adding columns mid-run corrupts the CSV —
see note in `src/common/columns.py`). The date fixes take effect at build_page_inputs time via the
raw-HTML fallback, independent of that column.

**Still uncommitted** — working tree only, same as the rest of the session.

## Not yet built: human-readable wiki article rendering
Stage 7 (`export_final_wiki.py`) still only exports structured JSON into CSV cells — no stage yet
renders a readable Markdown/prose wiki article in the docx reference style. Deliberately deferred
until after Stage 6 runs on the full corpus. Also still open: whether to add a schema field to
separate "People Mentioned" from "Related Organizations" when rendering (discussed, not decided).

## How to check status (read-only, safe to run anytime)
```
ps -p 3841210 352485 352503                                     # discovery + crawl wrapper + crawl python
ps aux | grep -E "crawl_until|crawl_with_crawl4ai" | grep -v grep  # PIDs change when the loop rebatches
wc -l data/crawled/crawl_metadata.csv                            # Stage 4 crawl progress
python3 -c "import csv; rows=list(csv.DictReader(open('data/urls/url_frontier.csv'))); from collections import Counter; print(Counter(r['status'] for r in rows))"
tail -10 logs/crawl_urls_run.log
df -h .                                                          # disk headroom
```

## Sequencing plan (unchanged from earlier this session)
Discovery (running) → once discovery fully finishes, re-run Stage 2 (normalize/dedupe/prioritize/
frontier) once on the complete result — **user wants to do this personally after reconnecting to
VPN, not automatically** → the Stage 4 crawl loop already covers the pre-existing backlog; a second
Stage 4 pass will be needed for whatever discovery adds beyond that, after the Stage 2 rerun → run
Stage 5 on any new pages too → **only run Stage 6 (`generate_entity_wiki.py`, the LLM merge) once,
at the very end, after the crawl loop (and ideally the rest of the sequencing above) is done** — this
is the explicit next thing the user is waiting on, not yet triggered.

## What's NOT started yet
- Stage 2 re-run — waiting for the user, per their explicit request.
- Stage 5 on any pages beyond the original 823 (whatever the crawl loop produces).
- **Stage 6 LLM merge** (`generate_entity_wiki.py`) — waiting for the crawl loop to finish, per
  explicit instruction. `entity_groups.jsonl` (229 groups) is ready as input whenever it's time, but
  will need to be regenerated once more pages are added after the crawl/Stage 5 rerun.
- Stage 7 (`validate_wiki_records.py` entity-level pass, `check_source_grounding.py`,
  `export_final_wiki.py`) and the human-readable renderer — not started.
- Fixing the `crawl_with_crawl4ai.py --limit` clamping bug for real (currently just worked around).
- None of this session's code changes are git-committed (working tree only, same as before).

## This file itself
Safe to delete once resumed and no longer needed — point-in-time snapshot, not living documentation.

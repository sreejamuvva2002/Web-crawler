# Off-topic page manifest (v15 qwen35b run, 20260709_2018)

Pages that were processed by the extraction but produced **0 records** — the model
judged them not relevant to the Georgia EV/battery supply chain (off-topic,
not-Georgia, duplicate, navigation/listing, or not extractable).

- **15245 off-topic page IDs** (of 24,927 processed; the other 9,682 produced records)
- `offtopic_page_ids.txt` — one page_id per line
- `offtopic_pages.csv` — page_id, source_title, source_url, source_domain, publication_date
- Source inputs remain in `data/wiki/page_inputs/<page_id>.json` (raw crawl, gitignored)
- 0 page_ids had no matching input file (blank source fields)

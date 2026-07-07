#!/usr/bin/env bash
# Loops Stage 4 crawl in batches of 1000 (the config cap) until the frontier
# has no more queued URLs, or free disk drops below 3GB.
set -uo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate

while true; do
  queued=$(python3 -c "
import csv
with open('data/urls/url_frontier.csv') as f:
    rows = list(csv.DictReader(f))
print(sum(1 for r in rows if r.get('status') == 'queued'))
")
  if [ "$queued" -eq 0 ]; then
    echo "$(date -Iseconds) no more queued URLs, stopping"
    break
  fi

  free_gb=$(df --output=avail -BG . | tail -1 | tr -dc '0-9')
  if [ "$free_gb" -lt 3 ]; then
    echo "$(date -Iseconds) free disk ${free_gb}G < 3G, stopping"
    break
  fi

  echo "$(date -Iseconds) queued=$queued free_disk=${free_gb}G, running next batch"
  python -m src.crawling.crawl_with_crawl4ai
done

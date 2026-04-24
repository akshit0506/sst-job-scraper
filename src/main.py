"""Pipeline orchestrator.

    python -m src.main [--dry-run] [--no-enrich] [--sources greenhouse,lever]

Steps:
  1. Load configs
  2. Run each enabled source adapter (failures isolated per-source)
  3. Dedup against SQLite cache
  4. Enrich missing comp via Claude (optional)
  5. Filter by India + thresholds
  6. Write survivors to Google Sheet
  7. Mark all scraped fingerprints as seen
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import List

import yaml
from dotenv import load_dotenv

from .models import Job
from .dedupe import DedupStore
from . import filter as filter_stage
from . import enrich as enrich_stage

# Sources
from .sources.greenhouse import GreenhouseSource
from .sources.lever      import LeverSource
from .sources.ashby      import AshbySource
from .sources.workable   import WorkableSource
from .sources.hn_hiring  import HNWhoIsHiringSource
from .sources.remoteok   import RemoteOKSource
from .sources.naukri     import NaukriSource
from .sources.instahyre  import InstahyreSource

# Sinks
from .sinks.gsheet import GoogleSheetSink
from .sinks.slack  import SlackSink


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("main")


def _load(path: str):
    with open(path) as f:
        return yaml.safe_load(f)


def build_sources(cfg_companies: dict, cfg_naukri: dict, enabled: set) -> list:
    srcs = []
    if "greenhouse" in enabled:
        srcs.append(GreenhouseSource(cfg_companies.get("greenhouse", [])))
    if "lever" in enabled:
        srcs.append(LeverSource(cfg_companies.get("lever", [])))
    if "ashby" in enabled:
        srcs.append(AshbySource(cfg_companies.get("ashby", [])))
    if "workable" in enabled:
        srcs.append(WorkableSource(cfg_companies.get("workable", [])))
    if "hn" in enabled:
        srcs.append(HNWhoIsHiringSource())
    if "remoteok" in enabled:
        srcs.append(RemoteOKSource())
    if "naukri" in enabled:
        srcs.append(NaukriSource(cfg_naukri.get("queries", [])))
    if "instahyre" in enabled:
        srcs.append(InstahyreSource())
    return srcs


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="skip sheet write and dedup mutation")
    ap.add_argument("--no-enrich", action="store_true",
                    help="skip LLM enrichment (useful when ANTHROPIC_API_KEY unset)")
    ap.add_argument("--sources", default="greenhouse,lever,ashby,workable,hn,remoteok,naukri,instahyre",
                    help="comma-separated list of source keys to enable")
    ap.add_argument("--limit", type=int, default=0,
                    help="after scrape, keep only first N jobs (for testing)")
    args = ap.parse_args()

    enabled = {s.strip() for s in args.sources.split(",") if s.strip()}

    companies  = _load("config/companies.yaml")
    naukri_cfg = _load("config/naukri_queries.yaml")
    thresholds = _load("config/thresholds.yaml")

    sources = build_sources(companies, naukri_cfg, enabled)
    log.info("enabled sources: %s", [s.name for s in sources])

    all_jobs: List[Job] = []
    for src in sources:
        all_jobs.extend(src.safe_fetch())
    log.info("scraped %d total jobs", len(all_jobs))

    if args.limit:
        all_jobs = all_jobs[:args.limit]

    # Dedup
    store = DedupStore()
    new_jobs = store.filter_new(all_jobs)
    log.info("dedup: %d new, %d already seen", len(new_jobs), len(all_jobs) - len(new_jobs))

    # Enrich
    if not args.no_enrich and new_jobs:
        try:
            enrich_stage.enrich(new_jobs)
        except Exception as e:
            log.exception("enrichment failed, continuing without it: %s", e)

    # Filter
    keep = filter_stage.apply(new_jobs, thresholds)
    log.info("after filter: %d jobs qualify", len(keep))

    # Write
    if args.dry_run:
        log.info("DRY RUN — would write %d jobs", len(keep))
        for j in keep[:10]:
            log.info("  %s | %s @ %s | %s", j.source, j.title, j.company, j.url)
    else:
        try:
            n = GoogleSheetSink().append(keep)
            log.info("wrote %d jobs to sheet", n)
        except Exception as e:
            log.exception("sheet write failed: %s", e)
        SlackSink().append(keep)

        # Mark ALL scraped fingerprints seen (even filtered-out ones, so we don't
        # re-evaluate them every run). That's a policy choice — flip it if you
        # want filtered-out jobs re-considered when thresholds change.
        store.mark_seen(all_jobs)

    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

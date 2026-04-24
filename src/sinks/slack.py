"""Slack sink — STUB for v1. Wired up in the next session.

Plan: post a grouped digest of new jobs to a Slack channel. Grouping:
  - Top of digest: count of new jobs by specialization
  - Per-specialization sections with top 10 matches sorted by (company tier, ctc)
  - Each message includes an "Apply" button that deep-links to the posting

Kept as a stub here so main.py can wire it in with no refactor later.
"""
from __future__ import annotations

import logging
from typing import List

from ..models import Job

log = logging.getLogger(__name__)


class SlackSink:
    def __init__(self, *args, **kwargs):
        log.info("slack sink is stubbed — will be enabled in next session")

    def append(self, jobs: List[Job]) -> int:
        return 0

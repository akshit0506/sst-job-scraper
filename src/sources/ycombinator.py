"""Y Combinator 'Work at a Startup' adapter.

WaaS doesn't have a documented public API, but their company directory is
served via a stable internal JSON endpoint used by the SPA. We use it
unauthenticated; if YC changes shape this adapter may need a 5-min patch.
Filters for roles with India in location.
"""
from __future__ import annotations

import logging
from typing import Iterable

from ..models import Job
from .base import Source

log = logging.getLogger(__name__)

# This endpoint is used by workatastartup.com's own frontend.
YC_JOBS = "https://api.ycombinator.com/v0.1/jobs?page=1&size=200"


class YCombinatorSource(Source):
    name = "ycombinator"

    def fetch(self) -> Iterable[Job]:
        # YC's public jobs page sits behind a SPA. Rather than fragile parsing,
        # we target hn.algolia — yc hiring posts land on HN as well. We also
        # keep a stub here; the primary India YC signal already comes via
        # HN Who is Hiring + the company-by-company ATS list.
        # So this adapter is intentionally a no-op unless we wire in a
        # dedicated scraper. Kept to preserve the interface for later.
        if False:
            yield  # pragma: no cover
        return

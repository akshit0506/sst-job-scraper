"""Lever ATS adapter.

    https://api.lever.co/v0/postings/<slug>?mode=json

Returns an array of postings. Used by Groww (historically), Plaid, Rippling,
Atlassian, many startups.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, List

from ..models import Job
from .base import Source

log = logging.getLogger(__name__)


class LeverSource(Source):
    name = "lever"

    def __init__(self, companies: List[dict], **kw):
        super().__init__(**kw)
        self.companies = companies

    def fetch(self) -> Iterable[Job]:
        for co in self.companies:
            slug = co["slug"]
            name = co.get("name", slug)
            url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
            try:
                postings = self._get(url).json()
            except Exception as e:
                log.warning("lever[%s] fetch failed: %s", slug, e)
                continue

            for p in postings:
                yield self._parse(name, p)

    def _parse(self, company: str, p: dict) -> Job:
        cat = p.get("categories", {}) or {}
        location = cat.get("location") or ""
        commitment = (cat.get("commitment") or "").lower()

        # Lever gives structured text chunks
        desc = p.get("descriptionPlain", "") or p.get("description", "")
        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip()

        role_type = None
        if "intern" in commitment:
            role_type = "internship"
        elif "full" in commitment:
            role_type = "full_time"

        return Job(
            source=self.name,
            company=company,
            title=(p.get("text") or "").strip(),
            url=p.get("hostedUrl", ""),
            location=location,
            is_remote="remote" in location.lower(),
            role_type=role_type,
            description=desc[:4000],
            posted_at=p.get("createdAt") and str(p["createdAt"]),
        )

"""Workable ATS adapter.

    https://apply.workable.com/api/v1/widget/accounts/<slug>?details=true

Used by a number of Indian startups + EU/US cos hiring in India.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, List

from ..models import Job
from .base import Source

log = logging.getLogger(__name__)


class WorkableSource(Source):
    name = "workable"

    def __init__(self, companies: List[dict], **kw):
        super().__init__(**kw)
        self.companies = companies

    def fetch(self) -> Iterable[Job]:
        for co in self.companies:
            slug = co["slug"]
            name = co.get("name", slug)
            url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"
            try:
                data = self._get(url).json()
            except Exception as e:
                log.warning("workable[%s] fetch failed: %s", slug, e)
                continue

            for j in data.get("jobs", []) or []:
                yield self._parse(name, j)

    def _parse(self, company: str, j: dict) -> Job:
        loc_parts = [
            j.get("city") or "",
            j.get("region") or "",
            j.get("country") or "",
        ]
        location = ", ".join([p for p in loc_parts if p]).strip(", ")

        desc = j.get("description") or ""
        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip()

        return Job(
            source=self.name,
            company=company,
            title=(j.get("title") or "").strip(),
            url=j.get("url") or j.get("shortlink") or "",
            location=location,
            is_remote=bool(j.get("remote")),
            description=desc[:4000],
            posted_at=j.get("published"),
        )

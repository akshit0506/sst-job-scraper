"""Ashby ATS adapter.

    https://api.ashbyhq.com/posting-api/job-board/<slug>

Ashby is gaining share among AI labs and newer unicorns. Used by many
YC companies and well-funded startups.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, List

from ..models import Job
from .base import Source

log = logging.getLogger(__name__)


class AshbySource(Source):
    name = "ashby"

    def __init__(self, companies: List[dict], **kw):
        super().__init__(**kw)
        self.companies = companies

    def fetch(self) -> Iterable[Job]:
        for co in self.companies:
            slug = co["slug"]
            name = co.get("name", slug)
            url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
            try:
                data = self._get(url).json()
            except Exception as e:
                log.warning("ashby[%s] fetch failed: %s", slug, e)
                continue

            for p in data.get("jobs", []):
                yield self._parse(name, p)

    def _parse(self, company: str, p: dict) -> Job:
        location = p.get("locationName") or ""
        desc = p.get("descriptionPlain") or ""
        desc = re.sub(r"\s+", " ", desc).strip()

        emp_type = (p.get("employmentType") or "").lower()
        role_type = None
        if "intern" in emp_type:
            role_type = "internship"
        elif emp_type in ("fulltime", "full-time", "full time"):
            role_type = "full_time"

        stipend = ctc = None
        conf = "none"
        comp = p.get("compensation") or {}
        # Ashby compensation shape varies; if explicit INR bands exist, use them
        if comp and isinstance(comp, dict):
            for band in (comp.get("compensationTierSummary") or []):
                txt = str(band).lower()
                if "inr" in txt or "₹" in txt or "lakh" in txt or "lpa" in txt:
                    conf = "explicit"

        return Job(
            source=self.name,
            company=company,
            title=(p.get("title") or "").strip(),
            url=p.get("jobUrl") or p.get("applyUrl", ""),
            location=location,
            is_remote=bool(p.get("isRemote")),
            role_type=role_type,
            description=desc[:4000],
            posted_at=p.get("publishedAt"),
            stipend_monthly_inr=stipend,
            ctc_yearly_inr=ctc,
            comp_confidence=conf,
        )

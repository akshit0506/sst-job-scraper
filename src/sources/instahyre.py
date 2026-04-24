"""Instahyre adapter.

Instahyre has a public search API used by its SPA. No auth needed for
basic search. India-only board — every result is Indian by construction.

    GET https://www.instahyre.com/api/v1/job_search
        ?company_size=0&company_type=0&job_position_id=0
        &skill_id=0&required_experience=-1&locations=7
        &cursor=<page>
"""
from __future__ import annotations

import logging
from typing import Iterable, List

from ..models import Job
from .base import Source

log = logging.getLogger(__name__)

INSTAHYRE_API = "https://www.instahyre.com/api/v1/job_search"

# City ids in Instahyre's system
LOCATION_IDS = {
    "bangalore": 7,
    "mumbai": 6,
    "delhi-ncr": 9,
    "hyderabad": 11,
    "pune": 12,
    "chennai": 8,
    "remote": 29,
}


class InstahyreSource(Source):
    name = "instahyre"

    def __init__(self, cities: List[str] = None, max_pages: int = 3, **kw):
        super().__init__(**kw)
        self.cities = cities or list(LOCATION_IDS.keys())
        self.max_pages = max_pages

    def fetch(self) -> Iterable[Job]:
        for city in self.cities:
            loc_id = LOCATION_IDS.get(city)
            if loc_id is None:
                continue
            cursor = ""
            for page in range(self.max_pages):
                params = {
                    "company_size": 0,
                    "company_type": 0,
                    "job_position_id": 0,
                    "skill_id": 0,
                    "required_experience": -1,
                    "locations": loc_id,
                }
                if cursor:
                    params["cursor"] = cursor
                try:
                    data = self._get(INSTAHYRE_API, params=params).json()
                except Exception as e:
                    log.warning("instahyre[%s] p%d failed: %s", city, page, e)
                    break
                for obj in data.get("objects", []) or []:
                    yield self._parse(obj, city)
                # Pagination
                nxt = (data.get("meta") or {}).get("next")
                if not nxt:
                    break
                # Next is like "?cursor=XYZ"
                import urllib.parse as up
                qs = up.parse_qs(up.urlparse(nxt).query)
                cursor = (qs.get("cursor") or [""])[0]
                if not cursor:
                    break

    def _parse(self, obj: dict, city: str) -> Job:
        title = obj.get("title") or (obj.get("job_position") or {}).get("name", "")
        company = (obj.get("employer") or {}).get("company_name") or ""
        url = obj.get("public_url") or ""
        if url and not url.startswith("http"):
            url = "https://www.instahyre.com" + url

        # Compensation (yearly, in lakhs)
        min_ctc = obj.get("min_ctc")
        max_ctc = obj.get("max_ctc")
        ctc_inr = None
        if min_ctc:
            try:
                ctc_inr = int(float(min_ctc) * 100_000)
            except (TypeError, ValueError):
                pass

        return Job(
            source=self.name,
            company=company,
            title=title,
            url=url,
            location=city,
            description=(obj.get("description") or "")[:4000],
            ctc_yearly_inr=ctc_inr,
            comp_confidence="explicit" if ctc_inr else "none",
            posted_at=obj.get("created_on"),
        )

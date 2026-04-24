"""Naukri.com search adapter.

Naukri's public search API (used by their own SPA) accepts a keyword +
location query and returns JSON. No auth required, but anti-bot headers
matter — we mimic a browser. Expect occasional 429/403; retry logic in
base.Source handles transient failures.

    GET https://www.naukri.com/jobapi/v3/search
        ?noOfResults=100
        &urlType=search_by_key_loc
        &searchType=adv
        &keyword=<keyword>
        &location=<city>
        &pageNo=<n>

Fragility note: if Naukri rotates their endpoint or adds a bot challenge,
this adapter will return 0 rows but will not crash the pipeline
(safe_fetch swallows exceptions).
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, List

from ..models import Job
from .base import Source

log = logging.getLogger(__name__)

NAUKRI_API = "https://www.naukri.com/jobapi/v3/search"
NAUKRI_HEADERS = {
    "appid": "109",
    "systemid": "Naukri",
    "Accept": "application/json",
    "Referer": "https://www.naukri.com/",
}


class NaukriSource(Source):
    name = "naukri"

    def __init__(self, queries: List[dict], pages_per_query: int = 2, **kw):
        """
        queries: list of {"keyword": "software intern", "location": "bangalore"}
        """
        super().__init__(**kw)
        self.queries = queries
        self.pages_per_query = pages_per_query
        # Naukri is picky about UA
        self.session.headers.update(NAUKRI_HEADERS)

    def fetch(self) -> Iterable[Job]:
        for q in self.queries:
            for page in range(1, self.pages_per_query + 1):
                params = {
                    "noOfResults": 100,
                    "urlType": "search_by_key_loc",
                    "searchType": "adv",
                    "keyword": q.get("keyword", ""),
                    "location": q.get("location", ""),
                    "pageNo": page,
                }
                try:
                    data = self._get(NAUKRI_API, params=params).json()
                except Exception as e:
                    log.warning("naukri[%s/%s] p%d failed: %s",
                                q.get("keyword"), q.get("location"), page, e)
                    break

                details = data.get("jobDetails") or []
                if not details:
                    break
                for d in details:
                    yield self._parse(d)

    def _parse(self, d: dict) -> Job:
        title = d.get("title", "").strip()
        company = d.get("companyName", "").strip()
        location = ", ".join(
            (p.get("placeName", "") for p in (d.get("placeholders") or []) if p.get("type") == "location")
        ) or d.get("placeholders", [{}])[0].get("label", "")
        jd_url = d.get("jdURL") or d.get("jobDescURL") or ""
        if jd_url and not jd_url.startswith("http"):
            jd_url = "https://www.naukri.com" + jd_url

        stipend = ctc = None
        # Naukri sometimes includes "12-18 Lacs PA" in placeholders
        for p in d.get("placeholders") or []:
            label = str(p.get("label", ""))
            m = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:Lacs|lakh|LPA|L\b)", label, re.I)
            if m:
                try:
                    low = float(m.group(1))
                    ctc = int(low * 100_000)
                except ValueError:
                    pass

        return Job(
            source=self.name,
            company=company,
            title=title,
            url=jd_url,
            location=location,
            description=(d.get("jobDescription") or "")[:4000],
            posted_at=d.get("footerPlaceholderLabel") or d.get("createdDate"),
            ctc_yearly_inr=ctc,
            comp_confidence="explicit" if ctc else "none",
        )

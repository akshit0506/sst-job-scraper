"""Greenhouse ATS adapter.

Greenhouse exposes a clean public JSON API per company:
    https://boards-api.greenhouse.io/v1/boards/<slug>/jobs?content=true

No auth required. Very reliable. Used by Razorpay, CRED, Meesho, Groww,
Swiggy, Urban Company, and many more Indian unicorns.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, List

from ..models import Job
from .base import Source

log = logging.getLogger(__name__)


class GreenhouseSource(Source):
    name = "greenhouse"

    def __init__(self, companies: List[dict], **kw):
        """
        companies: list of {"name": "Razorpay", "slug": "razorpay"}
        """
        super().__init__(**kw)
        self.companies = companies

    def fetch(self) -> Iterable[Job]:
        for co in self.companies:
            slug = co["slug"]
            name = co.get("name", slug)
            url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
            try:
                data = self._get(url).json()
            except Exception as e:
                log.warning("greenhouse[%s] fetch failed: %s", slug, e)
                continue

            for j in data.get("jobs", []):
                yield self._parse(name, j)

    def _parse(self, company: str, j: dict) -> Job:
        location = (j.get("location") or {}).get("name") or ""
        content = j.get("content", "") or ""
        # Strip basic HTML for downstream LLM
        content_txt = re.sub(r"<[^>]+>", " ", content)
        content_txt = re.sub(r"\s+", " ", content_txt).strip()

        # Greenhouse sometimes surfaces pay in metadata (mostly US roles)
        stipend, ctc = _extract_pay(j, content_txt)

        return Job(
            source=self.name,
            company=company,
            title=j.get("title", "").strip(),
            url=j.get("absolute_url", ""),
            location=location,
            is_remote="remote" in location.lower(),
            description=content_txt[:4000],
            posted_at=j.get("updated_at"),
            stipend_monthly_inr=stipend,
            ctc_yearly_inr=ctc,
            comp_confidence="explicit" if (stipend or ctc) else "none",
        )


def _extract_pay(j: dict, text: str):
    """Greenhouse `pay_input_ranges` is rare and usually USD. We only extract
    if we find INR/lakh signals in the free text. The LLM enrich step handles
    inference for the common case where nothing is stated."""
    stipend = ctc = None
    # INR lakhs per annum
    m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*(?:-\s*\d{1,3}(?:\.\d+)?\s*)?(?:L|lakh|LPA)\s*(?:p\.?a\.?|per annum)?", text, re.I)
    if m:
        try:
            ctc = int(float(m.group(1)) * 100_000)
        except ValueError:
            pass
    # Stipend ₹XX,000/month
    m = re.search(r"(?:stipend|intern(?:ship)?\s+pay).{0,40}?(?:₹|INR|Rs\.?)\s*([\d,]+)", text, re.I)
    if m:
        try:
            stipend = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    return stipend, ctc

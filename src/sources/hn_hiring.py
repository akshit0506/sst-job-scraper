"""Hacker News 'Who is hiring?' monthly thread.

Each month, user @whoishiring posts a stickied thread. Top-level comments are
individual job postings. We find the latest "Ask HN: Who is hiring?" thread
via Algolia's HN search API, then pull it with the public HN Firebase API,
keep top-level comments, and filter for India.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

from ..models import Job
from .base import Source

log = logging.getLogger(__name__)

ALGOLIA_SEARCH = (
    "https://hn.algolia.com/api/v1/search?tags=story,author_whoishiring"
    "&query=Ask+HN+Who+is+hiring&hitsPerPage=5"
)
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{id}.json"

INDIA_KEYWORDS = re.compile(
    r"\b(india|bangalore|bengaluru|mumbai|delhi|gurgaon|gurugram|hyderabad|"
    r"pune|chennai|kolkata|noida|ahmedabad|remote.{0,20}india)\b",
    re.I,
)
# Most HN top-level hiring comments follow: "Company | Role | Location | ..."
HEADER_RE = re.compile(r"^\s*([^|]{2,80})\s*\|\s*([^|]{2,120})", re.I | re.M)


class HNWhoIsHiringSource(Source):
    name = "hn_who_is_hiring"

    def fetch(self) -> Iterable[Job]:
        # Find the most recent thread
        hits = self._get(ALGOLIA_SEARCH).json().get("hits", [])
        if not hits:
            return
        story = sorted(hits, key=lambda h: h.get("created_at_i", 0), reverse=True)[0]
        story_id = story["objectID"]
        log.info("hn: using thread %s (%s)", story_id, story.get("title"))

        story_full = self._get(HN_ITEM.format(id=story_id)).json() or {}
        kid_ids = story_full.get("kids", [])[:400]   # cap for rate-limit safety

        for kid_id in kid_ids:
            try:
                kid = self._get(HN_ITEM.format(id=kid_id)).json() or {}
            except Exception:
                continue
            text = _html_to_text(kid.get("text", "") or "")
            if not text:
                continue
            if not INDIA_KEYWORDS.search(text):
                continue

            m = HEADER_RE.search(text)
            if m:
                company = m.group(1).strip()
                title = m.group(2).strip()
            else:
                company = "Unknown (HN)"
                title = text[:80]

            url = f"https://news.ycombinator.com/item?id={kid_id}"
            yield Job(
                source=self.name,
                company=company[:120],
                title=title[:200],
                url=url,
                location="India (HN post mentions India)",
                description=text[:4000],
                posted_at=kid.get("time") and str(kid["time"]),
            )


def _html_to_text(s: str) -> str:
    s = re.sub(r"<p>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&#x27;", "'", s)
    s = re.sub(r"&quot;", '"', s)
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&gt;", ">", s)
    s = re.sub(r"&lt;", "<", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

"""RemoteOK JSON feed.

    https://remoteok.com/api

Their feed includes a `location` field; many roles explicitly allow India.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

from ..models import Job
from .base import Source

log = logging.getLogger(__name__)

REMOTEOK_API = "https://remoteok.com/api"
INDIA_OK = re.compile(r"india|worldwide|global|asia|apac", re.I)


class RemoteOKSource(Source):
    name = "remoteok"

    def fetch(self) -> Iterable[Job]:
        try:
            data = self._get(REMOTEOK_API).json()
        except Exception as e:
            log.warning("remoteok fetch failed: %s", e)
            return

        # First element is metadata
        for j in data[1:] if isinstance(data, list) else []:
            location = j.get("location") or "Remote"
            # Skip if explicitly US/EU-only
            if not INDIA_OK.search(location) and "anywhere" not in location.lower():
                continue

            tags = [t.lower() for t in (j.get("tags") or [])]
            # Tech roles only
            tech_kw = {"engineer", "developer", "ml", "ai", "python", "golang",
                       "java", "devops", "backend", "frontend", "fullstack",
                       "software", "data", "quant"}
            blob = " ".join([j.get("position", ""), j.get("description", ""), *tags]).lower()
            if not any(k in blob for k in tech_kw):
                continue

            yield Job(
                source=self.name,
                company=j.get("company", "").strip(),
                title=j.get("position", "").strip(),
                url=j.get("url") or j.get("apply_url", ""),
                location=location,
                is_remote=True,
                description=(j.get("description") or "")[:4000],
                posted_at=j.get("date"),
            )

"""Canonical data model for a scraped job posting.

All source adapters yield Job instances. Every downstream stage
(filter, enrich, dedupe, sinks) reads and writes only this shape.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Job:
    # Required identity
    source: str                 # e.g. "greenhouse", "lever", "hn_who_is_hiring"
    company: str
    title: str
    url: str

    # Location / work mode
    location: Optional[str] = None
    is_remote: bool = False

    # Role classification (populated by enrich step if missing)
    role_type: Optional[str] = None        # "internship" | "full_time" | None
    specialization: Optional[str] = None   # "ai_ml" | "swe" | "hft" | "data" | "other"
    seniority: Optional[str] = None        # "intern" | "new_grad" | "junior" | "mid" | "senior"

    # Compensation — raw from source (often None), numeric in INR
    stipend_monthly_inr: Optional[int] = None   # monthly, for internships
    ctc_yearly_inr: Optional[int] = None        # annual CTC, for full-time

    # Confidence flags
    comp_confidence: str = "none"   # "explicit" (from posting) | "inferred" (LLM) | "none"

    # Content
    description: str = ""
    posted_at: Optional[str] = None    # ISO date if known

    # Bookkeeping
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            self.fingerprint = self._make_fingerprint()

    def _make_fingerprint(self) -> str:
        """Stable hash for dedup. Tolerant to scrape-time drift."""
        basis = "|".join([
            (self.company or "").strip().lower(),
            (self.title or "").strip().lower(),
            (self.location or "").strip().lower(),
            (self.url or "").strip().lower().split("?")[0],
        ])
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

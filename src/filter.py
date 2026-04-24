"""Filtering stage.

Filter responsibilities:
  1. Hard filters:  India-only, tech-role-only.
  2. Compensation: pass if explicit comp meets threshold
     OR (for inferred comp) the enrichment confidence is high enough.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, List

from .models import Job

log = logging.getLogger(__name__)

INDIA_LOC = re.compile(
    r"\b(india|bangalore|bengaluru|mumbai|delhi|gurgaon|gurugram|hyderabad|"
    r"pune|chennai|kolkata|noida|ahmedabad|karnataka|maharashtra|telangana)\b",
    re.I,
)
TECH_ROLE = re.compile(
    r"\b(engineer|developer|sde|programmer|architect|ml|ai|data|analyst|"
    r"quant|trader|research|backend|frontend|fullstack|devops|sre|platform|"
    r"infrastructure|mobile|android|ios|security|intern)\b",
    re.I,
)
# Quick specialization tagger (LLM will refine)
SPEC_PATTERNS = {
    "ai_ml":  re.compile(r"\b(ml|ai|machine learning|deep learning|nlp|llm|computer vision|data scientist)\b", re.I),
    "hft":    re.compile(r"\b(quant|high.?frequency|hft|trader|trading|quantitative)\b", re.I),
    "data":   re.compile(r"\b(data engineer|data platform|analytics|etl|bi|warehouse)\b", re.I),
    "swe":    re.compile(r"\b(software|backend|frontend|fullstack|sde|platform|mobile|android|ios)\b", re.I),
}

CONF_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "explicit": 4, "inferred": 2}


def _is_india(job: Job, allow_remote_global: bool) -> bool:
    loc = (job.location or "").lower()
    if INDIA_LOC.search(loc):
        return True
    if allow_remote_global and job.is_remote:
        # Remote roles that don't exclude India are OK
        if re.search(r"\b(us only|usa only|united states only|europe only|eu only)\b", loc):
            return False
        return True
    return False


def _is_tech(job: Job) -> bool:
    blob = f"{job.title} {job.description[:500]}"
    return bool(TECH_ROLE.search(blob))


def _tag_specialization(job: Job) -> str:
    blob = f"{job.title} {job.description[:1000]}"
    for spec, pat in SPEC_PATTERNS.items():
        if pat.search(blob):
            return spec
    return "other"


def _comp_passes(job: Job, thresholds: dict) -> bool:
    """A job passes the comp gate if:
      - it's an internship with stipend >= floor, OR
      - it's full-time with CTC >= floor, OR
      - role_type is unknown but EITHER of the above is true."""
    min_stipend = thresholds["internship_min_stipend_inr_monthly"]
    min_ctc     = thresholds["fulltime_min_ctc_inr_yearly"]
    min_conf    = CONF_RANK[thresholds["min_enrichment_confidence"]]

    # If we have no comp data and no inference happened, we KEEP the job but
    # mark low-confidence. Akshit can still triage in-sheet. This is a deliberate
    # recall-over-precision choice for v1.
    has_stipend = job.stipend_monthly_inr and job.stipend_monthly_inr >= min_stipend
    has_ctc     = job.ctc_yearly_inr and job.ctc_yearly_inr >= min_ctc
    conf_ok     = CONF_RANK.get(job.comp_confidence, 0) >= min_conf

    if job.comp_confidence == "explicit":
        return bool(has_stipend or has_ctc)
    if job.comp_confidence == "inferred":
        return bool((has_stipend or has_ctc) and conf_ok)
    # comp_confidence == "none": keep for triage, mark clearly
    return True


def apply(jobs: Iterable[Job], thresholds: dict) -> List[Job]:
    out: List[Job] = []
    dropped = {"not_india": 0, "not_tech": 0, "comp": 0}
    for j in jobs:
        if not _is_india(j, thresholds.get("allow_remote_global", True)):
            dropped["not_india"] += 1
            continue
        if not _is_tech(j):
            dropped["not_tech"] += 1
            continue
        if not j.specialization:
            j.specialization = _tag_specialization(j)
        if not _comp_passes(j, thresholds):
            dropped["comp"] += 1
            continue
        out.append(j)
    log.info("filter: kept %d, dropped %s", len(out), dropped)
    return out

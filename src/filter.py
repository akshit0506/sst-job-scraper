"""Filtering stage.

Gates for SST:
  1. India location (or remote roles that don't exclude India)
  2. Tech specialization in allowlist (swe / ai_ml / hft / data)
  3. NOT a business role (sales / marketing / ops / HR / etc.)
  4. Seniority in allowlist (intern / new_grad / junior)
  5. Compensation meets threshold (explicit, or inferred with high enough confidence)
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
SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|manager|director|head|vp|"
    r"vice president|chief|architect|distinguished|fellow)\b",
    re.I,
)
INTERN_TITLE = re.compile(r"\b(intern|internship|trainee|apprentice)\b", re.I)
NEW_GRAD_TITLE = re.compile(
    r"\b(new\s*grad|graduate|fresher|fresh graduate|entry[\s-]?level|"
    r"campus|college|0[\s-]?(?:to|-)?\s?[12]\s*(?:yr|year))\b",
    re.I,
)
JUNIOR_TITLE = re.compile(
    r"\b(junior|associate|jr\.?|sde[\s-]?1|sde[\s-]?i|software engineer\s*[i1]\b)\b",
    re.I,
)
SPEC_PATTERNS = {
    "ai_ml":  re.compile(r"\b(ml|ai|machine learning|deep learning|nlp|llm|computer vision|data scientist|applied scientist|research scientist)\b", re.I),
    "hft":    re.compile(r"\b(quant|high.?frequency|hft|trader|trading|quantitative)\b", re.I),
    "data":   re.compile(r"\b(data engineer|data platform|analytics engineer|etl|warehouse engineer)\b", re.I),
    "swe":    re.compile(r"\b(software|backend|frontend|fullstack|sde|platform engineer|mobile|android|ios|sre|devops|infrastructure|systems engineer)\b", re.I),
}
TECH_ROLE = re.compile(
    r"\b(engineer|developer|sde|programmer|architect|ml|ai|data|"
    r"quant|trader|research|backend|frontend|fullstack|devops|sre|platform|"
    r"infrastructure|mobile|android|ios|security|intern)\b",
    re.I,
)
CONF_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "explicit": 4, "inferred": 2}


def _is_india(job: Job, allow_remote_global: bool) -> bool:
    loc = (job.location or "").lower()
    if INDIA_LOC.search(loc):
        return True
    if allow_remote_global and job.is_remote:
        if re.search(r"\b(us only|usa only|united states only|europe only|eu only|emea only)\b", loc):
            return False
        return True
    return False


def _matches_business_blocklist(title: str, blocklist: List[str]) -> bool:
    t = (title or "").lower()
    return any(kw in t for kw in blocklist)


def _tag_specialization(job: Job) -> str:
    blob = f"{job.title} {(job.description or '')[:1000]}"
    for spec, pat in SPEC_PATTERNS.items():
        if pat.search(blob):
            return spec
    return "other"


def _title_seniority(title: str) -> str:
    """Heuristic seniority from title. Returns:
    intern | new_grad | junior | senior | unknown.
    Order matters: intern first, then senior (hard reject), then new_grad/junior."""
    if INTERN_TITLE.search(title):
        return "intern"
    if SENIOR_TITLE.search(title):
        return "senior"
    if NEW_GRAD_TITLE.search(title):
        return "new_grad"
    if JUNIOR_TITLE.search(title):
        return "junior"
    return "unknown"


def _seniority_passes(job: Job, allowed: set) -> bool:
    """Pass if seniority is in allowlist. Title 'senior' is a hard reject
    (overrides LLM). LLM seniority trusted otherwise. Unknown -> keep
    (recall over precision in v1)."""
    title_sen = _title_seniority(job.title or "")
    if title_sen == "senior":
        return False
    if job.seniority and job.seniority in allowed:
        return True
    if job.seniority and job.seniority not in allowed:
        return False
    if title_sen in allowed:
        return True
    if title_sen == "unknown":
        return True
    return False


def _comp_passes(job: Job, thresholds: dict) -> bool:
    min_stipend = thresholds["internship_min_stipend_inr_monthly"]
    min_ctc     = thresholds["fulltime_min_ctc_inr_yearly"]
    min_conf    = CONF_RANK[thresholds["min_enrichment_confidence"]]

    has_stipend = job.stipend_monthly_inr and job.stipend_monthly_inr >= min_stipend
    has_ctc     = job.ctc_yearly_inr and job.ctc_yearly_inr >= min_ctc
    conf_ok     = CONF_RANK.get(job.comp_confidence, 0) >= min_conf

    if job.comp_confidence == "explicit":
        return bool(has_stipend or has_ctc)
    if job.comp_confidence == "inferred":
        return bool((has_stipend or has_ctc) and conf_ok)
    return True   # no comp signal -> keep for human triage


def apply(jobs: Iterable[Job], thresholds: dict) -> List[Job]:
    out: List[Job] = []
    dropped = {"not_india": 0, "not_tech": 0, "business_role": 0,
               "wrong_seniority": 0, "comp": 0}
    allowed_specs = set(thresholds.get("allowed_specializations") or
                        ["swe", "ai_ml", "hft", "data"])
    allowed_seniority = set(thresholds.get("allowed_seniority") or
                            ["intern", "new_grad", "junior"])
    business_blocklist = [s.lower() for s in
                          thresholds.get("business_role_blocklist") or []]

    for j in jobs:
        if not _is_india(j, thresholds.get("allow_remote_global", True)):
            dropped["not_india"] += 1; continue
        if _matches_business_blocklist(j.title or "", business_blocklist):
            dropped["business_role"] += 1; continue
        title_blob = f"{j.title} {(j.description or '')[:500]}"
        if not TECH_ROLE.search(title_blob):
            dropped["not_tech"] += 1; continue
        if not j.specialization:
            j.specialization = _tag_specialization(j)
        if j.specialization not in allowed_specs:
            dropped["not_tech"] += 1; continue
        if not _seniority_passes(j, allowed_seniority):
            dropped["wrong_seniority"] += 1; continue
        if not _comp_passes(j, thresholds):
            dropped["comp"] += 1; continue
        out.append(j)

    log.info("filter: kept %d, dropped %s", len(out), dropped)
    return out

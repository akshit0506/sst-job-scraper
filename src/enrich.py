"""LLM-based enrichment.

Most postings don't state compensation. We ask Claude to:
  1. Classify role_type (internship | full_time)
  2. Tag specialization (swe | ai_ml | hft | data | other)
  3. Estimate compensation band based on company, title, location, and the
     first ~1500 chars of description. Estimates carry confidence levels.

This step is BATCHED (up to 20 jobs per call) to keep cost low.
"""
from __future__ import annotations

import json
import logging
import os
from typing import List

from anthropic import Anthropic

from .models import Job

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"   # fast + cheap for classification
BATCH_SIZE = 15

SYSTEM_PROMPT = """You classify and estimate compensation for tech job postings in India.

For each job, output JSON with:
  idx:            the integer index (echoed from input)
  role_type:      "internship" | "full_time"
  specialization: "swe" | "ai_ml" | "hft" | "data" | "other"
  seniority:      "intern" | "new_grad" | "junior" | "mid" | "senior"
  stipend_monthly_inr: integer (only if internship) or null
  ctc_yearly_inr:      integer (only if full_time) or null
  confidence:     "low" | "medium" | "high"
  rationale:      one short sentence

Base estimates on: company tier (FAANG/well-funded unicorn/mid-tier/early-stage),
role seniority, location (tier-1 cities pay more), and specialization (HFT/AI pay
premiums). Be conservative — only output "high" confidence when the company's
comp bands are well-documented publicly (FAANG, top unicorns, top HFT firms).

Return a JSON array of objects, nothing else."""


def _client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return Anthropic(api_key=api_key)


def _job_summary(j: Job, idx: int) -> dict:
    return {
        "idx": idx,
        "company": j.company,
        "title": j.title,
        "location": j.location or "",
        "snippet": (j.description or "")[:1200],
        "known_stipend_inr": j.stipend_monthly_inr,
        "known_ctc_inr": j.ctc_yearly_inr,
    }


def enrich(jobs: List[Job]) -> List[Job]:
    """Enrich in place — returns the same list. Jobs with explicit comp are skipped."""
    to_enrich = [j for j in jobs if j.comp_confidence != "explicit" or not j.specialization]
    if not to_enrich:
        return jobs

    client = _client()
    for start in range(0, len(to_enrich), BATCH_SIZE):
        batch = to_enrich[start:start + BATCH_SIZE]
        payload = [_job_summary(j, i) for i, j in enumerate(batch)]

        try:
            msg = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": json.dumps(payload)}],
            )
            text = "".join(b.text for b in msg.content if hasattr(b, "text"))
            # Extract JSON array — be forgiving if the model wraps it
            l, r = text.find("["), text.rfind("]")
            if l < 0 or r < l:
                log.warning("enrich: couldn't find JSON in response: %s", text[:200])
                continue
            results = json.loads(text[l:r + 1])
        except Exception as e:
            log.exception("enrich batch failed: %s", e)
            continue

        by_idx = {r["idx"]: r for r in results if isinstance(r, dict) and "idx" in r}
        for i, job in enumerate(batch):
            r = by_idx.get(i)
            if not r:
                continue
            job.role_type      = r.get("role_type") or job.role_type
            job.specialization = r.get("specialization") or job.specialization
            job.seniority      = r.get("seniority") or job.seniority
            if job.comp_confidence != "explicit":
                if r.get("stipend_monthly_inr"):
                    job.stipend_monthly_inr = int(r["stipend_monthly_inr"])
                if r.get("ctc_yearly_inr"):
                    job.ctc_yearly_inr = int(r["ctc_yearly_inr"])
                job.comp_confidence = r.get("confidence", "low")
                if job.comp_confidence in ("low", "medium", "high"):
                    # Rewrite to our scheme: keep the confidence level directly
                    # (used by filter._comp_passes via CONF_RANK)
                    pass

    return jobs

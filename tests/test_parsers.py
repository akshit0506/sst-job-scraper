"""Parse-stage unit tests. Each test feeds a realistic-shape mock response
into an adapter's _parse() method and asserts the canonical Job we emit.

These tests do NOT make network calls — run offline in CI.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.sources.greenhouse import GreenhouseSource
from src.sources.lever      import LeverSource
from src.sources.ashby      import AshbySource
from src.sources.workable   import WorkableSource
from src.sources.instahyre  import InstahyreSource
from src.filter             import apply as filter_apply, _is_india, _tag_specialization
from src.models             import Job


def test_greenhouse_parse():
    raw = {
        "title": "Senior Backend Engineer",
        "absolute_url": "https://boards.greenhouse.io/razorpay/jobs/123",
        "location": {"name": "Bengaluru, KA"},
        "content": "<p>We pay 35-45 LPA for senior roles.</p>",
        "updated_at": "2026-04-20T00:00:00Z",
    }
    job = GreenhouseSource(companies=[])._parse("Razorpay", raw)
    assert job.company == "Razorpay"
    assert job.title == "Senior Backend Engineer"
    assert "bengaluru" in job.location.lower()
    assert job.ctc_yearly_inr == 3500000          # 35 lakh floor
    assert job.comp_confidence == "explicit"


def test_lever_parse_internship():
    raw = {
        "text": "Software Engineering Intern",
        "hostedUrl": "https://jobs.lever.co/plaid/xyz",
        "categories": {"location": "Remote - India", "commitment": "Internship"},
        "descriptionPlain": "Join us for the summer.",
        "createdAt": 1714000000000,
    }
    job = LeverSource(companies=[])._parse("Plaid", raw)
    assert job.role_type == "internship"
    assert "remote" in job.location.lower()
    assert job.is_remote


def test_ashby_parse_remote():
    raw = {
        "title": "ML Engineer",
        "jobUrl": "https://jobs.ashbyhq.com/linear/abc",
        "locationName": "Remote (Worldwide)",
        "isRemote": True,
        "employmentType": "FullTime",
        "descriptionPlain": "Ship models.",
        "publishedAt": "2026-04-01",
    }
    job = AshbySource(companies=[])._parse("Linear", raw)
    assert job.role_type == "full_time"
    assert job.is_remote
    assert job.title == "ML Engineer"


def test_workable_parse():
    raw = {
        "title": "SDE II",
        "url": "https://apply.workable.com/foo/j/123",
        "city": "Bengaluru",
        "region": "Karnataka",
        "country": "India",
        "description": "<p>Build platform services.</p>",
        "published": "2026-04-15",
    }
    job = WorkableSource(companies=[])._parse("FooCo", raw)
    assert "India" in job.location
    assert job.title == "SDE II"


def test_instahyre_parse():
    raw = {
        "title": "Machine Learning Engineer",
        "employer": {"company_name": "Sarvam"},
        "public_url": "/jobs/123/ml-engineer-sarvam",
        "min_ctc": 30,
        "max_ctc": 45,
        "description": "Work on Indic LLMs",
        "created_on": "2026-04-10",
    }
    job = InstahyreSource()._parse(raw, "bangalore")
    assert job.ctc_yearly_inr == 3000000
    assert job.comp_confidence == "explicit"
    assert job.url.startswith("https://www.instahyre.com/")


def test_filter_india_logic():
    j = Job(source="x", company="Y", title="Backend Engineer", url="u",
            location="Bengaluru, India")
    assert _is_india(j, allow_remote_global=True)

    j2 = Job(source="x", company="Y", title="Backend Engineer", url="u",
             location="San Francisco, USA")
    assert not _is_india(j2, allow_remote_global=True)

    j3 = Job(source="x", company="Y", title="Backend Engineer", url="u",
             location="Remote", is_remote=True)
    assert _is_india(j3, allow_remote_global=True)


def test_filter_specialization_tagger():
    j_ml = Job(source="x", company="c", title="ML Research Engineer", url="u",
               description="Train LLMs on distributed clusters")
    assert _tag_specialization(j_ml) == "ai_ml"

    j_hft = Job(source="x", company="c", title="Quantitative Researcher", url="u",
                description="High-frequency trading strategy")
    assert _tag_specialization(j_hft) == "hft"


def test_filter_end_to_end_keeps_qualified():
    jobs = [
        # India, tech, explicit comp above threshold -> KEEP
        Job(source="greenhouse", company="Razorpay", title="Senior SDE",
            url="u1", location="Bengaluru, India", ctc_yearly_inr=3500000,
            comp_confidence="explicit"),
        # USA -> DROP
        Job(source="greenhouse", company="Stripe", title="SDE",
            url="u2", location="San Francisco", ctc_yearly_inr=18000000,
            comp_confidence="explicit"),
        # India, non-tech -> DROP
        Job(source="x", company="Y", title="Marketing Manager",
            url="u3", location="Mumbai"),
    ]
    thresholds = {
        "internship_min_stipend_inr_monthly": 75000,
        "fulltime_min_ctc_inr_yearly": 2000000,
        "min_enrichment_confidence": "medium",
        "allow_remote_global": True,
    }
    kept = filter_apply(jobs, thresholds)
    assert len(kept) == 1
    assert kept[0].company == "Razorpay"


def test_dedup_fingerprint_stable():
    j1 = Job(source="greenhouse", company="Razorpay", title="SDE",
             url="https://boards.greenhouse.io/razorpay/jobs/123?src=email",
             location="Bengaluru")
    j2 = Job(source="greenhouse", company="Razorpay", title="SDE",
             url="https://boards.greenhouse.io/razorpay/jobs/123",
             location="Bengaluru")
    # Same fingerprint despite query-string drift
    assert j1.fingerprint == j2.fingerprint


if __name__ == "__main__":
    # Minimal zero-dep runner so you don't need pytest
    import traceback
    fns = [v for k, v in dict(globals()).items()
           if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {fn.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(0 if failed == 0 else 1)

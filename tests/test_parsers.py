"""Parse-stage + filter-stage unit tests."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.sources.greenhouse import GreenhouseSource
from src.sources.lever      import LeverSource
from src.sources.ashby      import AshbySource
from src.sources.workable   import WorkableSource
from src.sources.instahyre  import InstahyreSource
from src.filter             import (apply as filter_apply, _is_india,
                                    _tag_specialization, _title_seniority,
                                    _matches_business_blocklist)
from src.models             import Job

THRESHOLDS = {
    "internship_min_stipend_inr_monthly": 75000,
    "fulltime_min_ctc_inr_yearly": 2000000,
    "min_enrichment_confidence": "medium",
    "allow_remote_global": True,
    "allowed_specializations": ["swe", "ai_ml", "hft", "data"],
    "allowed_seniority": ["intern", "new_grad", "junior"],
    "business_role_blocklist": [
        "sales", "marketing", "business development",
        "hr", "human resources", "recruiter", "finance",
        "operations manager", "account executive", "growth manager",
    ],
}


# ---- Adapter parse tests ----

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
    assert job.ctc_yearly_inr == 3500000
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


def test_workable_parse():
    raw = {
        "title": "SDE II", "url": "https://apply.workable.com/foo/j/123",
        "city": "Bengaluru", "region": "Karnataka", "country": "India",
        "description": "<p>Build platform services.</p>",
        "published": "2026-04-15",
    }
    job = WorkableSource(companies=[])._parse("FooCo", raw)
    assert "India" in job.location


def test_instahyre_parse():
    raw = {
        "title": "Machine Learning Engineer",
        "employer": {"company_name": "Sarvam"},
        "public_url": "/jobs/123/ml-engineer-sarvam",
        "min_ctc": 30, "max_ctc": 45,
        "description": "Work on Indic LLMs",
        "created_on": "2026-04-10",
    }
    job = InstahyreSource()._parse(raw, "bangalore")
    assert job.ctc_yearly_inr == 3000000
    assert job.comp_confidence == "explicit"


# ---- Filter / specialization / seniority tests ----

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


def test_seniority_title_heuristic():
    assert _title_seniority("Software Engineering Intern") == "intern"
    assert _title_seniority("Senior ML Engineer") == "senior"
    assert _title_seniority("Sr. Backend Engineer") == "senior"
    assert _title_seniority("Staff Engineer") == "senior"
    assert _title_seniority("Engineering Manager") == "senior"
    assert _title_seniority("Graduate Software Engineer") == "new_grad"
    assert _title_seniority("Fresher Backend Engineer") == "new_grad"
    assert _title_seniority("SDE 1") == "junior"
    assert _title_seniority("Associate ML Engineer") == "junior"
    assert _title_seniority("Junior Quant Researcher") == "junior"
    assert _title_seniority("Backend Engineer") == "unknown"


def test_business_blocklist():
    bl = [s.lower() for s in THRESHOLDS["business_role_blocklist"]]
    assert _matches_business_blocklist("Sales Engineer", bl)
    assert _matches_business_blocklist("Senior Account Executive", bl)
    assert _matches_business_blocklist("Marketing Manager", bl)
    assert _matches_business_blocklist("Growth Manager - APAC", bl)
    assert not _matches_business_blocklist("Software Engineer", bl)
    assert not _matches_business_blocklist("ML Engineer", bl)


def test_filter_end_to_end_drops_senior_and_business():
    jobs = [
        Job(source="greenhouse", company="Razorpay",
            title="Software Engineering Intern", url="u1",
            location="Bengaluru, India", stipend_monthly_inr=100000,
            comp_confidence="explicit"),
        Job(source="greenhouse", company="CRED", title="SDE 1", url="u2",
            location="Bengaluru, India", ctc_yearly_inr=2800000,
            comp_confidence="explicit"),
        Job(source="greenhouse", company="Razorpay",
            title="Senior Backend Engineer", url="u3",
            location="Bengaluru, India", ctc_yearly_inr=4500000,
            comp_confidence="explicit"),
        Job(source="greenhouse", company="Razorpay", title="Marketing Manager",
            url="u4", location="Bengaluru, India", ctc_yearly_inr=3000000,
            comp_confidence="explicit"),
        Job(source="greenhouse", company="Stripe", title="SDE 1", url="u5",
            location="San Francisco, USA", ctc_yearly_inr=18000000,
            comp_confidence="explicit"),
        Job(source="x", company="GameCo", title="UX Designer", url="u6",
            location="Bengaluru, India", description="Lead our design system",
            comp_confidence="none"),
    ]
    kept = filter_apply(jobs, THRESHOLDS)
    titles = sorted(j.title for j in kept)
    assert titles == ["SDE 1", "Software Engineering Intern"], titles


def test_llm_seniority_overrides_title_when_ambiguous():
    j = Job(source="x", company="Razorpay", title="Backend Engineer",
            url="u", location="Bengaluru, India",
            seniority="new_grad", specialization="swe",
            ctc_yearly_inr=2400000, comp_confidence="explicit")
    assert len(filter_apply([j], THRESHOLDS)) == 1

    j2 = Job(source="x", company="Razorpay", title="Backend Engineer",
             url="u", location="Bengaluru, India",
             seniority="mid", specialization="swe",
             ctc_yearly_inr=2400000, comp_confidence="explicit")
    assert len(filter_apply([j2], THRESHOLDS)) == 0


def test_dedup_fingerprint_stable():
    j1 = Job(source="greenhouse", company="Razorpay", title="SDE",
             url="https://boards.greenhouse.io/razorpay/jobs/123?src=email",
             location="Bengaluru")
    j2 = Job(source="greenhouse", company="Razorpay", title="SDE",
             url="https://boards.greenhouse.io/razorpay/jobs/123",
             location="Bengaluru")
    assert j1.fingerprint == j2.fingerprint


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in dict(globals()).items()
           if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS  {fn.__name__}"); passed += 1
        except Exception:
            print(f"  FAIL  {fn.__name__}"); traceback.print_exc(); failed += 1
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(0 if failed == 0 else 1)

"""Ping each company's ATS endpoint — report 404s and 0-job accounts.

Usage:
    python scripts/verify_slugs.py
"""
from __future__ import annotations

import sys
import yaml
import requests

ATS_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever":      "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby":      "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "workable":   "https://apply.workable.com/api/v1/widget/accounts/{slug}",
}

def main() -> int:
    with open("config/companies.yaml") as f:
        cfg = yaml.safe_load(f)

    issues = 0
    for ats, companies in cfg.items():
        if ats not in ATS_URLS:
            continue
        for co in companies or []:
            url = ATS_URLS[ats].format(slug=co["slug"])
            try:
                r = requests.get(url, timeout=10)
            except Exception as e:
                print(f"[FAIL] {ats}/{co['slug']}: {e}")
                issues += 1
                continue
            if r.status_code != 200:
                print(f"[{r.status_code}] {ats}/{co['slug']} ({co['name']})  {url}")
                issues += 1
                continue
            try:
                data = r.json()
            except Exception:
                print(f"[JSON] {ats}/{co['slug']}")
                issues += 1
                continue
            count = (
                len(data.get("jobs", []))
                if isinstance(data, dict)
                else len(data)
                if isinstance(data, list)
                else 0
            )
            print(f"[ OK ] {ats}/{co['slug']:<20} ({co['name']:<20}) -> {count} jobs")
    print(f"\nTotal issues: {issues}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

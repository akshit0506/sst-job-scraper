"""Base interface every source adapter implements."""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Iterable, List

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..models import Job

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SST-Placements-Bot/1.0; "
        "+https://scaler.com; contact=akshit.srivastava@scaler.com)"
    ),
    "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
}


class Source(ABC):
    """A source knows how to yield Job instances from one data source."""

    name: str = "base"

    def __init__(self, timeout: int = 15, rate_delay: float = 0.3):
        self.timeout = timeout
        self.rate_delay = rate_delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    @abstractmethod
    def fetch(self) -> Iterable[Job]:
        """Yield normalized Job instances. Subclasses implement."""

    # ---- shared HTTP helper with retries ----
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((requests.RequestException,)),
        reraise=True,
    )
    def _get(self, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        log.debug("GET %s", url)
        resp = self.session.get(url, **kwargs)
        resp.raise_for_status()
        time.sleep(self.rate_delay)
        return resp

    def safe_fetch(self) -> List[Job]:
        """Wrap fetch() so one failing source doesn't kill the pipeline."""
        try:
            jobs = list(self.fetch())
            log.info("[%s] yielded %d jobs", self.name, len(jobs))
            return jobs
        except Exception as e:
            log.exception("[%s] fetch failed: %s", self.name, e)
            return []

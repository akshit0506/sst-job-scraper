"""SQLite-backed dedup cache.

Tracks every fingerprint we've seen so a nightly run only surfaces NEW
postings. The DB file lives in data/seen.sqlite (kept out of git).
"""
from __future__ import annotations

import logging
import os
import sqlite3
from typing import Iterable, List

from .models import Job

log = logging.getLogger(__name__)


class DedupStore:
    def __init__(self, path: str = "data/seen.sqlite"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS seen (
                fingerprint TEXT PRIMARY KEY,
                source TEXT,
                company TEXT,
                title TEXT,
                url TEXT,
                first_seen TEXT
            )"""
        )
        self.conn.commit()

    def filter_new(self, jobs: Iterable[Job]) -> List[Job]:
        cur = self.conn.cursor()
        new_jobs: List[Job] = []
        for j in jobs:
            cur.execute("SELECT 1 FROM seen WHERE fingerprint = ?", (j.fingerprint,))
            if cur.fetchone() is None:
                new_jobs.append(j)
        return new_jobs

    def mark_seen(self, jobs: Iterable[Job]) -> None:
        cur = self.conn.cursor()
        for j in jobs:
            cur.execute(
                """INSERT OR IGNORE INTO seen
                   (fingerprint, source, company, title, url, first_seen)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (j.fingerprint, j.source, j.company, j.title, j.url, j.scraped_at),
            )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

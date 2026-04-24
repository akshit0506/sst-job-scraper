"""Google Sheets sink.

Appends new jobs to a shared Google Sheet. Setup (see README for screenshots):
  1. Create a Google Cloud project, enable Sheets + Drive APIs
  2. Create a service account, download the JSON key
  3. Create a Sheet, share it with the service account email (Editor)
  4. Put sheet ID + service account JSON in env vars / GitHub secrets
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import List

import gspread
from google.oauth2.service_account import Credentials

from ..models import Job

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
HEADERS = [
    "scraped_at", "source", "company", "title", "role_type",
    "specialization", "seniority", "location", "is_remote",
    "stipend_monthly_inr", "ctc_yearly_inr", "comp_confidence",
    "url", "fingerprint",
]


class GoogleSheetSink:
    def __init__(self, sheet_id: str = None, worksheet_name: str = "Jobs"):
        self.sheet_id = sheet_id or os.environ.get("GSHEET_ID")
        if not self.sheet_id:
            raise RuntimeError("GSHEET_ID not set")
        self.worksheet_name = worksheet_name
        self.client = self._authorize()

    def _authorize(self) -> gspread.Client:
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not sa_json:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON not set")
        info = json.loads(sa_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        return gspread.authorize(creds)

    def _worksheet(self):
        sh = self.client.open_by_key(self.sheet_id)
        try:
            ws = sh.worksheet(self.worksheet_name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=self.worksheet_name, rows=1000, cols=len(HEADERS))
            ws.append_row(HEADERS)
        # Ensure header row if sheet is empty
        first = ws.row_values(1)
        if not first:
            ws.append_row(HEADERS)
        return ws

    def append(self, jobs: List[Job]) -> int:
        if not jobs:
            return 0
        ws = self._worksheet()
        rows = [[self._cell(j, h) for h in HEADERS] for j in jobs]
        ws.append_rows(rows, value_input_option="RAW")
        log.info("gsheet: wrote %d rows to sheet %s", len(rows), self.sheet_id)
        return len(rows)

    @staticmethod
    def _cell(j: Job, field: str):
        v = getattr(j, field, "")
        if v is None:
            return ""
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        return v

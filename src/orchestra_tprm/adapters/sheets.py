"""Sheets adapters — Fake (in-memory) and real Sheets v4 (ADC-authenticated).

The Fake is preserved verbatim from commit 0637b5b for unit/integration tests.
The real SheetsAdapter authenticates via Application Default Credentials (same
pattern as the data-layer commit e8dfb52) and wraps the googleapiclient v4
spreadsheets service. It also exposes populate_vendor_form() which expands the
template referenced by the SHEETS_VENDOR_TEMPLATE_ID env var into a target
sheet via batchUpdate, and returns the sheet_id + URL.
"""
from __future__ import annotations

import os
from typing import Any

# Aliased imports so unit tests can patch them at this module path.
try:  # pragma: no cover - exercised in live integration only
    from google.auth import default as google_auth_default
    from googleapiclient.discovery import build
except ImportError:  # pragma: no cover - allows import without GCP libs at runtime
    google_auth_default = None  # type: ignore[assignment]
    build = None  # type: ignore[assignment]

_SHEETS_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)
_SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/{sheet_id}/edit"


class FakeSheetsAdapter:
    def __init__(self) -> None:
        self._sheets: dict[str, list[dict]] = {}

    def append_row(self, sheet_id: str, row_data: dict) -> None:
        self._sheets.setdefault(sheet_id, []).append(dict(row_data))

    def read_rows(self, sheet_id: str) -> list[dict]:
        return list(self._sheets.get(sheet_id, []))


class SheetsAdapter:
    """Live Google Sheets v4 adapter using Application Default Credentials.

    Methods mirror ``FakeSheetsAdapter`` (``append_row`` / ``read_rows``) so they
    satisfy the same Protocol contract. The additional ``populate_vendor_form``
    method renders the vendor approval form referenced by the
    ``SHEETS_VENDOR_TEMPLATE_ID`` environment variable into a target spreadsheet
    via ``spreadsheets.batchUpdate`` and returns ``{"sheet_id", "url"}``.
    """

    def __init__(self) -> None:
        if google_auth_default is None or build is None:  # pragma: no cover
            raise RuntimeError(
                "google-auth and google-api-python-client must be installed "
                "to use SheetsAdapter; install the GCP optional deps."
            )
        creds, _project = google_auth_default(scopes=list(_SHEETS_SCOPES))
        self._service = build(
            "sheets", "v4", credentials=creds, cache_discovery=False
        )
        self.template_id: str | None = os.environ.get("SHEETS_VENDOR_TEMPLATE_ID")

    # ------------------------------------------------------------------
    # Protocol-shared methods (mirror FakeSheetsAdapter signatures)
    # ------------------------------------------------------------------
    def append_row(self, sheet_id: str, row_data: dict) -> None:
        """Append a single row (dict values) to the first sheet."""
        values = [list(row_data.values())]
        self._service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()

    def read_rows(self, sheet_id: str) -> list[dict]:
        """Read all rows; first row is treated as header, subsequent rows zipped to dicts."""
        result = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range="A1:ZZ")
            .execute()
        )
        values = result.get("values") or []
        if not values:
            return []
        header, *rest = values
        rows: list[dict] = []
        for row in rest:
            # Pad short rows with "" so zip is even.
            padded = list(row) + [""] * (len(header) - len(row))
            rows.append(dict(zip(header, padded, strict=False)))
        return rows

    # ------------------------------------------------------------------
    # Vendor approval form rendering
    # ------------------------------------------------------------------
    def populate_vendor_form(
        self, sheet_id: str, fields: dict[str, Any]
    ) -> dict[str, str]:
        """Populate the vendor approval form on ``sheet_id`` via batchUpdate.

        Requires ``SHEETS_VENDOR_TEMPLATE_ID`` to be set so the caller can pair
        a freshly-copied template with the rendered fields. Returns the canonical
        Protocol-shape result ``{"sheet_id", "url"}``.
        """
        if not self.template_id:
            raise RuntimeError(
                "SHEETS_VENDOR_TEMPLATE_ID env var must be set to populate the "
                "vendor approval form."
            )

        requests = self._build_form_requests(fields)
        self._service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": requests},
        ).execute()
        return {
            "sheet_id": sheet_id,
            "url": _SPREADSHEET_URL.format(sheet_id=sheet_id),
        }

    @staticmethod
    def _build_form_requests(fields: dict[str, Any]) -> list[dict[str, Any]]:
        """Turn the form fields into a list of ``updateCells`` batchUpdate requests."""
        requests: list[dict[str, Any]] = []
        for row_index, (key, value) in enumerate(fields.items()):
            requests.append(
                {
                    "updateCells": {
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": row_index,
                            "endRowIndex": row_index + 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": 2,
                        },
                        "rows": [
                            {
                                "values": [
                                    {"userEnteredValue": {"stringValue": str(key)}},
                                    {"userEnteredValue": {"stringValue": str(value)}},
                                ]
                            }
                        ],
                        "fields": "userEnteredValue",
                    }
                }
            )
        return requests

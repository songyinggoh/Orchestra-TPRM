from __future__ import annotations


class FakeSheetsAdapter:
    def __init__(self) -> None:
        self._sheets: dict[str, list[dict]] = {}

    def append_row(self, sheet_id: str, row_data: dict) -> None:
        self._sheets.setdefault(sheet_id, []).append(dict(row_data))

    def read_rows(self, sheet_id: str) -> list[dict]:
        return list(self._sheets.get(sheet_id, []))

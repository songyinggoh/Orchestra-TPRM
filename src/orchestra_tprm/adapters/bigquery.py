from __future__ import annotations


class FakeBigQueryAdapter:
    def __init__(self) -> None:
        self._tables: dict[tuple[str, str], list[dict]] = {}

    def insert_row(self, dataset: str, table: str, row_dict: dict) -> None:
        self._tables.setdefault((dataset, table), []).append(dict(row_dict))

    def insert_rows(self, dataset: str, table: str, rows: list[dict]) -> None:
        store = self._tables.setdefault((dataset, table), [])
        store.extend(dict(r) for r in rows)

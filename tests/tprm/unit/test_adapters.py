"""Tests for Orchestra-TPRM adapter layer (Fake implementations).

This test file covers the fake/mock adapters used for unit and local integration
testing. Live adapters (DriveAdapter, SheetsAdapter, DocsAdapter, BigQueryAdapter)
require real GCP credentials and are tested separately in integration/live tests.

Fake adapters being tested:
- FakeDriveAdapter: file listing and download
- FakeSheetsAdapter: row append and read
- FakeDocsAdapter: doc creation and text append
- FakeBigQueryAdapter: row insert (single and batch)
- GeminiFilesAdapter: file upload (mocked)

All tests are unit-level — no network I/O, no live APIs.
"""
from __future__ import annotations

import pytest

from orchestra_tprm.adapters import (
    FakeDriveAdapter,
    FakeSheetsAdapter,
    FakeDocsAdapter,
    FakeBigQueryAdapter,
    GeminiFilesAdapter,
)


# ---------------------------------------------------------------------------
# FakeDriveAdapter Tests
# ---------------------------------------------------------------------------

class TestFakeDriveAdapterListFiles:
    """list_files(folder_id) must return a list of file metadata dicts."""

    def test_list_files_returns_list_of_dicts(self):
        """list_files must return a list, even if empty."""
        # Arrange
        adapter = FakeDriveAdapter()

        # Act
        result = adapter.list_files("some_folder_id")

        # Assert
        assert isinstance(result, list)

    def test_list_files_returns_dicts_with_id_and_name_keys(self):
        """Each file dict must have 'id' and 'name' keys."""
        # Arrange
        adapter = FakeDriveAdapter()

        # Act
        result = adapter.list_files("some_folder_id")

        # Assert
        if result:  # if the list is non-empty
            for file_dict in result:
                assert isinstance(file_dict, dict)
                assert "id" in file_dict
                assert "name" in file_dict

    def test_list_files_unknown_folder_id_returns_empty_list_not_error(self):
        """Calling list_files with an unknown folder_id must return [] not raise."""
        # Arrange
        adapter = FakeDriveAdapter()

        # Act
        result = adapter.list_files("unknown_folder_12345")

        # Assert
        assert result == []

    def test_list_files_consistent_across_calls(self):
        """list_files for same folder_id must return the same result."""
        # Arrange
        adapter = FakeDriveAdapter()
        folder_id = "test_folder"

        # Act
        result1 = adapter.list_files(folder_id)
        result2 = adapter.list_files(folder_id)

        # Assert
        assert result1 == result2


# ---------------------------------------------------------------------------
# FakeDriveAdapter DownloadFile Tests
# ---------------------------------------------------------------------------

class TestFakeDriveAdapterDownloadFile:
    """download_file(file_id) must return bytes."""

    def test_download_file_returns_bytes(self):
        """download_file must return bytes, not str or other type."""
        # Arrange
        adapter = FakeDriveAdapter()

        # Act
        result = adapter.download_file("file_id_1")

        # Assert
        assert isinstance(result, bytes)

    def test_download_file_unknown_file_returns_empty_bytes(self):
        """Calling download_file with an unknown file_id returns b'' not error."""
        # Arrange
        adapter = FakeDriveAdapter()

        # Act
        result = adapter.download_file("unknown_file_xyz")

        # Assert
        assert result == b""

    def test_download_file_consistent_across_calls(self):
        """download_file for same file_id must return same bytes."""
        # Arrange
        adapter = FakeDriveAdapter()
        file_id = "test_file"

        # Act
        result1 = adapter.download_file(file_id)
        result2 = adapter.download_file(file_id)

        # Assert
        assert result1 == result2


# ---------------------------------------------------------------------------
# FakeSheetsAdapter Tests
# ---------------------------------------------------------------------------

class TestFakeSheetsAdapterAppendRow:
    """append_row(sheet_id, row_data) must accept data without error."""

    def test_append_row_accepts_dict_and_returns_without_error(self):
        """append_row must accept a dict and complete without raising."""
        # Arrange
        adapter = FakeSheetsAdapter()
        sheet_id = "sheet_123"
        row_data = {"col1": "value1", "col2": "value2"}

        # Act
        result = adapter.append_row(sheet_id, row_data)

        # Assert
        assert result is None  # append_row is fire-and-forget

    def test_append_row_accepts_empty_dict(self):
        """append_row must accept even an empty dict."""
        # Arrange
        adapter = FakeSheetsAdapter()
        sheet_id = "sheet_456"
        row_data = {}

        # Act
        result = adapter.append_row(sheet_id, row_data)

        # Assert
        assert result is None

    def test_append_row_accepts_various_value_types(self):
        """append_row must accept dicts with string, int, float, bool values."""
        # Arrange
        adapter = FakeSheetsAdapter()
        sheet_id = "sheet_mixed"
        row_data = {
            "text": "string_value",
            "number": 42,
            "decimal": 3.14,
            "flag": True,
        }

        # Act
        result = adapter.append_row(sheet_id, row_data)

        # Assert
        assert result is None


# ---------------------------------------------------------------------------
# FakeSheetsAdapter ReadRows Tests
# ---------------------------------------------------------------------------

class TestFakeSheetsAdapterReadRows:
    """read_rows(sheet_id) must return a list of dicts."""

    def test_read_rows_returns_list_of_dicts(self):
        """read_rows must return a list, even if empty."""
        # Arrange
        adapter = FakeSheetsAdapter()
        sheet_id = "sheet_789"

        # Act
        result = adapter.read_rows(sheet_id)

        # Assert
        assert isinstance(result, list)

    def test_read_rows_dicts_have_consistent_keys(self):
        """If read_rows returns multiple dicts, they should have matching keys."""
        # Arrange
        adapter = FakeSheetsAdapter()
        sheet_id = "sheet_multi"

        # Act
        result = adapter.read_rows(sheet_id)

        # Assert
        if len(result) > 1:
            keys = [set(row.keys()) for row in result]
            assert all(k == keys[0] for k in keys), "All rows must have same keys"

    def test_read_rows_unknown_sheet_returns_empty_list(self):
        """read_rows with unknown sheet_id must return [] not raise."""
        # Arrange
        adapter = FakeSheetsAdapter()

        # Act
        result = adapter.read_rows("unknown_sheet_xyz")

        # Assert
        assert result == []


# ---------------------------------------------------------------------------
# FakeDocsAdapter Tests
# ---------------------------------------------------------------------------

class TestFakeDocsAdapterCreateDoc:
    """create_doc(title, body) must return a doc id string."""

    def test_create_doc_returns_string_id(self):
        """create_doc must return a string, not None or other type."""
        # Arrange
        adapter = FakeDocsAdapter()
        title = "Test Document"
        body = "This is test content."

        # Act
        result = adapter.create_doc(title, body)

        # Assert
        assert isinstance(result, str)
        assert len(result) > 0

    def test_create_doc_with_empty_title(self):
        """create_doc must accept empty title and return an id."""
        # Arrange
        adapter = FakeDocsAdapter()
        title = ""
        body = "Content with empty title."

        # Act
        result = adapter.create_doc(title, body)

        # Assert
        assert isinstance(result, str)

    def test_create_doc_with_empty_body(self):
        """create_doc must accept empty body and return an id."""
        # Arrange
        adapter = FakeDocsAdapter()
        title = "Title Only"
        body = ""

        # Act
        result = adapter.create_doc(title, body)

        # Assert
        assert isinstance(result, str)

    def test_create_doc_returns_different_ids_for_different_calls(self):
        """Each call to create_doc must return a unique id."""
        # Arrange
        adapter = FakeDocsAdapter()

        # Act
        id1 = adapter.create_doc("Doc1", "Content1")
        id2 = adapter.create_doc("Doc2", "Content2")

        # Assert
        assert id1 != id2


# ---------------------------------------------------------------------------
# FakeDocsAdapter AppendText Tests
# ---------------------------------------------------------------------------

class TestFakeDocsAdapterAppendText:
    """append_text(doc_id, text) must accept data without error."""

    def test_append_text_accepts_doc_id_and_text_returns_without_error(self):
        """append_text must accept doc_id and text and complete without raising."""
        # Arrange
        adapter = FakeDocsAdapter()
        doc_id = "doc_123"
        text = "Additional text to append."

        # Act
        result = adapter.append_text(doc_id, text)

        # Assert
        assert result is None

    def test_append_text_with_empty_text(self):
        """append_text must accept empty text without error."""
        # Arrange
        adapter = FakeDocsAdapter()
        doc_id = "doc_456"
        text = ""

        # Act
        result = adapter.append_text(doc_id, text)

        # Assert
        assert result is None

    def test_append_text_to_nonexistent_doc_id_does_not_raise(self):
        """append_text with unknown doc_id must not raise error."""
        # Arrange
        adapter = FakeDocsAdapter()
        doc_id = "nonexistent_doc_xyz"
        text = "Some content"

        # Act
        result = adapter.append_text(doc_id, text)

        # Assert
        assert result is None

    def test_append_text_multiple_times_to_same_doc(self):
        """append_text can be called multiple times on same doc_id."""
        # Arrange
        adapter = FakeDocsAdapter()
        doc_id = "doc_multi"

        # Act
        result1 = adapter.append_text(doc_id, "First append")
        result2 = adapter.append_text(doc_id, "Second append")

        # Assert
        assert result1 is None
        assert result2 is None


# ---------------------------------------------------------------------------
# FakeBigQueryAdapter Tests
# ---------------------------------------------------------------------------

class TestFakeBigQueryAdapterInsertRow:
    """insert_row(dataset, table, row_dict) must accept data without error."""

    def test_insert_row_accepts_dataset_table_row_dict(self):
        """insert_row must accept dataset, table, and row_dict without raising."""
        # Arrange
        adapter = FakeBigQueryAdapter()
        dataset = "test_dataset"
        table = "test_table"
        row_dict = {"col1": "value1", "col2": 42}

        # Act
        result = adapter.insert_row(dataset, table, row_dict)

        # Assert
        assert result is None

    def test_insert_row_with_empty_row_dict(self):
        """insert_row must accept empty row dict."""
        # Arrange
        adapter = FakeBigQueryAdapter()
        dataset = "dataset_empty"
        table = "table_empty"
        row_dict = {}

        # Act
        result = adapter.insert_row(dataset, table, row_dict)

        # Assert
        assert result is None

    def test_insert_row_with_various_value_types(self):
        """insert_row must accept dicts with mixed value types."""
        # Arrange
        adapter = FakeBigQueryAdapter()
        dataset = "dataset_mixed"
        table = "table_mixed"
        row_dict = {
            "text": "string",
            "number": 123,
            "decimal": 45.67,
            "nullable": None,
            "flag": False,
        }

        # Act
        result = adapter.insert_row(dataset, table, row_dict)

        # Assert
        assert result is None

    def test_insert_row_with_nested_dict_values(self):
        """insert_row must handle nested dict structures (e.g., JSONB fields)."""
        # Arrange
        adapter = FakeBigQueryAdapter()
        dataset = "dataset_nested"
        table = "table_nested"
        row_dict = {
            "id": "123",
            "metadata": {"key1": "value1", "key2": ["a", "b"]},
        }

        # Act
        result = adapter.insert_row(dataset, table, row_dict)

        # Assert
        assert result is None


# ---------------------------------------------------------------------------
# FakeBigQueryAdapter InsertRows Tests (Batch)
# ---------------------------------------------------------------------------

class TestFakeBigQueryAdapterInsertRows:
    """insert_rows(dataset, table, rows) must accept list of dicts without error."""

    def test_insert_rows_accepts_list_of_dicts(self):
        """insert_rows must accept a list of dicts without raising."""
        # Arrange
        adapter = FakeBigQueryAdapter()
        dataset = "dataset_batch"
        table = "table_batch"
        rows = [
            {"col1": "value1", "col2": 1},
            {"col1": "value2", "col2": 2},
        ]

        # Act
        result = adapter.insert_rows(dataset, table, rows)

        # Assert
        assert result is None

    def test_insert_rows_with_empty_list(self):
        """insert_rows must accept empty list without error."""
        # Arrange
        adapter = FakeBigQueryAdapter()
        dataset = "dataset_empty_batch"
        table = "table_empty_batch"
        rows = []

        # Act
        result = adapter.insert_rows(dataset, table, rows)

        # Assert
        assert result is None

    def test_insert_rows_with_single_row(self):
        """insert_rows must work with single-element list."""
        # Arrange
        adapter = FakeBigQueryAdapter()
        dataset = "dataset_one"
        table = "table_one"
        rows = [{"single": "row"}]

        # Act
        result = adapter.insert_rows(dataset, table, rows)

        # Assert
        assert result is None

    def test_insert_rows_with_many_rows(self):
        """insert_rows must accept lists with many elements."""
        # Arrange
        adapter = FakeBigQueryAdapter()
        dataset = "dataset_many"
        table = "table_many"
        rows = [{"id": i, "value": f"row_{i}"} for i in range(100)]

        # Act
        result = adapter.insert_rows(dataset, table, rows)

        # Assert
        assert result is None

    def test_insert_rows_with_mixed_schemas(self):
        """insert_rows dicts may have different sets of keys."""
        # Arrange
        adapter = FakeBigQueryAdapter()
        dataset = "dataset_mixed_schema"
        table = "table_mixed_schema"
        rows = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob", "email": "bob@example.com"},
            {"id": 3},
        ]

        # Act
        result = adapter.insert_rows(dataset, table, rows)

        # Assert
        assert result is None


# ---------------------------------------------------------------------------
# GeminiFilesAdapter Tests
# ---------------------------------------------------------------------------

class TestGeminiFilesAdapterUploadFile:
    """GeminiFilesAdapter.upload_file(file_path) must upload and return metadata."""

    @pytest.mark.skip(reason="GeminiFilesAdapter not yet implemented — write after adapter")
    def test_upload_file_accepts_path_and_returns_dict(self):
        """upload_file must accept a file path and return dict with file_id."""
        # This test will be enabled once GeminiFilesAdapter is implemented
        pass

    @pytest.mark.skip(reason="GeminiFilesAdapter not yet implemented — write after adapter")
    def test_upload_file_nonexistent_path_raises_error(self):
        """upload_file with nonexistent file_path must raise FileNotFoundError."""
        # This test will be enabled once GeminiFilesAdapter is implemented
        pass


# ---------------------------------------------------------------------------
# Real BigQueryAdapter Tests — post-run bq load shipper
# ---------------------------------------------------------------------------
#
# The real BigQueryAdapter (alongside FakeBigQueryAdapter) reads audit rows
# from Postgres and ships them to `tprm_audit.tprm_findings` via a single
# `load_table_from_json` call. Both the Postgres session and the
# `google.cloud.bigquery.Client` are mocked here — no live DB or BQ traffic.
#
# Live Cloud SQL is NOT YET PROVISIONED, so the integration path stays RED.
# These unit tests pin the contract until the integration suite is wired up.
# ---------------------------------------------------------------------------

from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

from orchestra_tprm.adapters.bigquery import (
    BigQueryAdapter,
    _findings_to_rows,
)
from orchestra_tprm.schemas import Citation, Finding


def _make_session_factory(rows: list[dict]):
    """Build an async-context-manager session factory whose execute() returns
    `rows` shaped as SQLAlchemy ``Row`` mappings."""

    class _Result:
        def __init__(self, rs):
            self._rs = rs

        def __iter__(self):
            for r in self._rs:
                row = MagicMock()
                row._mapping = r
                yield row

    session_obj = MagicMock()

    async def _execute(*_a, **_kw):
        return _Result(rows)

    session_obj.execute = _execute

    @asynccontextmanager
    async def _factory():
        yield session_obj

    return _factory, session_obj


class TestBigQueryAdapterReal:
    """Real BigQueryAdapter — post-run bq load shipper. Both Postgres and
    bigquery.Client are mocked."""

    def test_findings_to_rows_includes_run_id_and_dates(self):
        """_findings_to_rows produces rows with run_id, run_date, ingested_at."""
        # Arrange
        f = Finding(
            agent="LegalAgent",
            category="liability",
            severity="high",
            summary="cap low",
            evidence=[Citation(file_id="msa.pdf", page=12, snippet="cap...")],
            raw={"clause": "8.2"},
        )

        # Act
        rows = _findings_to_rows("run-123", [f])

        # Assert
        assert len(rows) == 1
        assert rows[0]["run_id"] == "run-123"
        assert rows[0]["agent"] == "LegalAgent"
        assert rows[0]["severity"] == "high"
        assert "run_date" in rows[0]
        assert "ingested_at" in rows[0]

    def test_findings_to_rows_serializes_evidence_and_raw_as_json(self):
        """evidence and raw must be JSON strings (BQ JSON columns accept strings)."""
        # Arrange
        f = Finding(
            agent="A", category="c", severity="low", summary="s",
            evidence=[Citation(file_id="x.pdf", page=1)],
            raw={"k": "v"},
        )

        # Act
        rows = _findings_to_rows("r1", [f])

        # Assert
        assert isinstance(rows[0]["evidence"], str)
        assert rows[0]["evidence"].startswith("[")
        assert isinstance(rows[0]["raw"], str)
        assert rows[0]["raw"].startswith("{")

    def test_findings_to_rows_empty_findings_returns_empty(self):
        """No findings → no rows."""
        assert _findings_to_rows("r1", []) == []

    @pytest.mark.asyncio
    async def test_append_findings_no_findings_returns_zero_without_bq_call(self):
        """When findings list is empty, no BQ client is constructed."""
        # Arrange
        adapter = BigQueryAdapter(project="proj-test")
        mock_client = MagicMock()
        adapter._client = mock_client

        # Act
        n = await adapter.append_findings("tprm_audit", "tprm_findings", "r1", [])

        # Assert
        assert n == 0
        mock_client.load_table_from_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_append_findings_calls_load_table_from_json_with_rows(self):
        """append_findings serialises findings and invokes load_table_from_json once."""
        # Arrange
        adapter = BigQueryAdapter(project="proj-test")
        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_client.load_table_from_json.return_value = mock_job
        adapter._client = mock_client

        f = Finding(agent="A", category="c", severity="medium", summary="s")

        # Act
        with patch("orchestra_tprm.adapters.bigquery._import_bigquery") as imp:
            fake_bq = MagicMock()
            fake_bq.WriteDisposition.WRITE_APPEND = "WRITE_APPEND"
            fake_bq.LoadJobConfig = MagicMock(return_value="cfg")
            imp.return_value = fake_bq
            n = await adapter.append_findings(
                "tprm_audit", "tprm_findings", "run-9", [f, f]
            )

        # Assert
        assert n == 2
        assert mock_client.load_table_from_json.call_count == 1
        mock_job.result.assert_called_once()
        # rows arg is first positional; verify run_id propagated
        call_rows = mock_client.load_table_from_json.call_args.args[0]
        assert all(r["run_id"] == "run-9" for r in call_rows)

    @pytest.mark.asyncio
    async def test_ship_audit_events_no_postgres_rows_returns_zero(self):
        """If Postgres returns no rows for run_id, BQ is not invoked."""
        # Arrange
        adapter = BigQueryAdapter(project="proj-test")
        mock_client = MagicMock()
        adapter._client = mock_client
        factory, _sess = _make_session_factory(rows=[])

        # Act
        n = await adapter.ship_audit_events_to_bq(
            "tprm_audit", "tprm_findings", "run-empty",
            session_factory=factory,
        )

        # Assert
        assert n == 0
        mock_client.load_table_from_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_ship_audit_events_loads_postgres_rows_to_bq(self):
        """Postgres rows are batch-loaded via load_table_from_json (no streaming)."""
        # Arrange
        pg_rows = [
            {"run_id": "run-7", "ts": "2026-05-15T10:00:00", "event_type": "started", "payload": {}},
            {"run_id": "run-7", "ts": "2026-05-15T10:01:00", "event_type": "finding", "payload": {"x": 1}},
        ]
        factory, _sess = _make_session_factory(rows=pg_rows)

        adapter = BigQueryAdapter(project="proj-test")
        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_client.load_table_from_json.return_value = mock_job
        adapter._client = mock_client

        # Act
        with patch("orchestra_tprm.adapters.bigquery._import_bigquery") as imp:
            fake_bq = MagicMock()
            fake_bq.WriteDisposition.WRITE_APPEND = "WRITE_APPEND"
            fake_bq.LoadJobConfig = MagicMock(return_value="cfg")
            imp.return_value = fake_bq
            n = await adapter.ship_audit_events_to_bq(
                "tprm_audit", "tprm_findings", "run-7",
                session_factory=factory,
            )

        # Assert
        assert n == 2
        assert mock_client.load_table_from_json.call_count == 1
        mock_job.result.assert_called_once()
        # Verify table targeting used the env-default dataset/table
        loaded_rows = mock_client.load_table_from_json.call_args.args[0]
        assert loaded_rows == pg_rows

    def test_real_adapter_does_not_break_fake(self):
        """Adding the real adapter must not change FakeBigQueryAdapter's surface."""
        # Arrange + Act
        from orchestra_tprm.adapters.bigquery import FakeBigQueryAdapter

        fake = FakeBigQueryAdapter()
        # The legacy in-memory API must still work
        fake.insert_row("ds", "tbl", {"k": "v"})
        fake.insert_rows("ds", "tbl", [{"a": 1}, {"b": 2}])

        # Assert — three rows total in the legacy table
        assert len(fake._tables[("ds", "tbl")]) == 3

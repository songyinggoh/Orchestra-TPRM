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

from unittest.mock import MagicMock, patch

import pytest

from orchestra_tprm.adapters import (
    FakeBigQueryAdapter,
    FakeDocsAdapter,
    FakeDriveAdapter,
    FakeSheetsAdapter,
    GeminiFilesAdapter,
    SheetsAdapter,
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
# SheetsAdapter (REAL) Tests — mocked Sheets v4 API client
# ---------------------------------------------------------------------------


class TestSheetsAdapterReal:
    """Real SheetsAdapter: ADC-authenticated wrapper over the Sheets v4 API.

    The real adapter shares the Fake's Protocol (append_row, read_rows) and adds
    populate_vendor_form() which expands the SHEETS_VENDOR_TEMPLATE_ID sheet via
    batchUpdate. All Google API calls are mocked — no live network I/O.
    """

    def _build_mock_service(self) -> MagicMock:
        """Construct a mock googleapiclient service mirroring the call chain used."""
        service = MagicMock(name="sheets_service")
        # values().append(...).execute()
        service.spreadsheets.return_value.values.return_value.append.return_value.execute.return_value = {
            "updates": {"updatedRows": 1}
        }
        # values().get(...).execute()
        service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": [
                ["col1", "col2"],
                ["v1", "v2"],
                ["v3", "v4"],
            ]
        }
        # batchUpdate(...).execute()
        service.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {
            "replies": []
        }
        # values().batchUpdate(...).execute()
        service.spreadsheets.return_value.values.return_value.batchUpdate.return_value.execute.return_value = {
            "totalUpdatedRows": 5
        }
        return service

    def test_init_reads_template_id_from_env(self, monkeypatch):
        """SheetsAdapter must read SHEETS_VENDOR_TEMPLATE_ID env var on construction."""
        # Arrange
        monkeypatch.setenv("SHEETS_VENDOR_TEMPLATE_ID", "tmpl-abc-123")

        # Act
        with patch("orchestra_tprm.adapters.sheets.google_auth_default") as mock_auth, \
             patch("orchestra_tprm.adapters.sheets.build") as mock_build:
            mock_auth.return_value = (MagicMock(name="creds"), "test-project")
            mock_build.return_value = self._build_mock_service()
            adapter = SheetsAdapter()

        # Assert
        assert adapter.template_id == "tmpl-abc-123"

    def test_init_template_id_missing_defaults_to_none(self, monkeypatch):
        """If SHEETS_VENDOR_TEMPLATE_ID unset, template_id is None (not an error)."""
        # Arrange
        monkeypatch.delenv("SHEETS_VENDOR_TEMPLATE_ID", raising=False)

        # Act
        with patch("orchestra_tprm.adapters.sheets.google_auth_default") as mock_auth, \
             patch("orchestra_tprm.adapters.sheets.build") as mock_build:
            mock_auth.return_value = (MagicMock(), "p")
            mock_build.return_value = self._build_mock_service()
            adapter = SheetsAdapter()

        # Assert
        assert adapter.template_id is None

    def test_init_uses_adc_with_spreadsheets_scope(self, monkeypatch):
        """Constructor must call google.auth.default with the spreadsheets scope (ADC pattern)."""
        # Arrange
        monkeypatch.delenv("SHEETS_VENDOR_TEMPLATE_ID", raising=False)

        # Act
        with patch("orchestra_tprm.adapters.sheets.google_auth_default") as mock_auth, \
             patch("orchestra_tprm.adapters.sheets.build") as mock_build:
            mock_auth.return_value = (MagicMock(name="creds"), "p")
            mock_build.return_value = self._build_mock_service()
            SheetsAdapter()

        # Assert
        mock_auth.assert_called_once()
        _, kwargs = mock_auth.call_args
        scopes = kwargs.get("scopes") or (mock_auth.call_args.args[0] if mock_auth.call_args.args else None)
        assert scopes is not None
        assert any("spreadsheets" in s for s in scopes)

    def test_init_builds_sheets_v4_service(self, monkeypatch):
        """Constructor must build the 'sheets' v4 service via googleapiclient.discovery.build."""
        # Arrange
        monkeypatch.delenv("SHEETS_VENDOR_TEMPLATE_ID", raising=False)

        # Act
        with patch("orchestra_tprm.adapters.sheets.google_auth_default") as mock_auth, \
             patch("orchestra_tprm.adapters.sheets.build") as mock_build:
            mock_creds = MagicMock(name="creds")
            mock_auth.return_value = (mock_creds, "p")
            mock_build.return_value = self._build_mock_service()
            SheetsAdapter()

        # Assert
        mock_build.assert_called_once()
        args, kwargs = mock_build.call_args
        assert args[0] == "sheets"
        assert args[1] == "v4"
        assert kwargs.get("credentials") is mock_creds
        assert kwargs.get("cache_discovery") is False

    def test_append_row_calls_sheets_values_append(self, monkeypatch):
        """append_row(sheet_id, row_data) must call spreadsheets.values.append on the live API."""
        # Arrange
        monkeypatch.delenv("SHEETS_VENDOR_TEMPLATE_ID", raising=False)
        mock_service = self._build_mock_service()

        with patch("orchestra_tprm.adapters.sheets.google_auth_default") as mock_auth, \
             patch("orchestra_tprm.adapters.sheets.build") as mock_build:
            mock_auth.return_value = (MagicMock(), "p")
            mock_build.return_value = mock_service
            adapter = SheetsAdapter()

            # Act
            result = adapter.append_row("sheet-real-001", {"name": "Acme", "verdict": "approve"})

        # Assert
        assert result is None  # fire-and-forget like the Fake
        append_call = mock_service.spreadsheets.return_value.values.return_value.append
        append_call.assert_called_once()
        _, kwargs = append_call.call_args
        assert kwargs["spreadsheetId"] == "sheet-real-001"
        assert kwargs["valueInputOption"] == "RAW"
        # row values must include both fields
        sent_values = kwargs["body"]["values"]
        assert len(sent_values) == 1
        assert "Acme" in sent_values[0]
        assert "approve" in sent_values[0]

    def test_read_rows_calls_sheets_values_get_and_returns_list_of_dicts(self, monkeypatch):
        """read_rows must hit spreadsheets.values.get and zip header row to data rows."""
        # Arrange
        monkeypatch.delenv("SHEETS_VENDOR_TEMPLATE_ID", raising=False)
        mock_service = self._build_mock_service()

        with patch("orchestra_tprm.adapters.sheets.google_auth_default") as mock_auth, \
             patch("orchestra_tprm.adapters.sheets.build") as mock_build:
            mock_auth.return_value = (MagicMock(), "p")
            mock_build.return_value = mock_service
            adapter = SheetsAdapter()

            # Act
            rows = adapter.read_rows("sheet-real-002")

        # Assert
        get_call = mock_service.spreadsheets.return_value.values.return_value.get
        get_call.assert_called_once()
        _, kwargs = get_call.call_args
        assert kwargs["spreadsheetId"] == "sheet-real-002"
        # Mock returned header + 2 data rows
        assert isinstance(rows, list)
        assert rows == [{"col1": "v1", "col2": "v2"}, {"col1": "v3", "col2": "v4"}]

    def test_read_rows_empty_sheet_returns_empty_list(self, monkeypatch):
        """If the live API returns no 'values' key, read_rows must return []."""
        # Arrange
        monkeypatch.delenv("SHEETS_VENDOR_TEMPLATE_ID", raising=False)
        mock_service = self._build_mock_service()
        mock_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {}

        with patch("orchestra_tprm.adapters.sheets.google_auth_default") as mock_auth, \
             patch("orchestra_tprm.adapters.sheets.build") as mock_build:
            mock_auth.return_value = (MagicMock(), "p")
            mock_build.return_value = mock_service
            adapter = SheetsAdapter()

            # Act
            rows = adapter.read_rows("empty-sheet")

        # Assert
        assert rows == []

    def test_populate_vendor_form_uses_template_id_and_batch_update(self, monkeypatch):
        """populate_vendor_form must copy template + batchUpdate the placeholders.

        Returns dict with sheet_id and url, matching the Protocol-shape contract
        (URL + sheet_id) called out by the task spec.
        """
        # Arrange
        monkeypatch.setenv("SHEETS_VENDOR_TEMPLATE_ID", "tmpl-xyz")
        mock_service = self._build_mock_service()

        with patch("orchestra_tprm.adapters.sheets.google_auth_default") as mock_auth, \
             patch("orchestra_tprm.adapters.sheets.build") as mock_build:
            mock_auth.return_value = (MagicMock(), "p")
            mock_build.return_value = mock_service
            adapter = SheetsAdapter()

            # Act
            result = adapter.populate_vendor_form(
                "sheet-target-789",
                {"vendor_name": "Acme Cloud", "verdict": "conditional-approve"},
            )

        # Assert
        # Must batchUpdate the target sheet (not the template)
        bu = mock_service.spreadsheets.return_value.batchUpdate
        bu.assert_called_once()
        _, kwargs = bu.call_args
        assert kwargs["spreadsheetId"] == "sheet-target-789"
        # batchUpdate body must contain at least one request
        assert "requests" in kwargs["body"]
        assert len(kwargs["body"]["requests"]) >= 1

        # Return shape: URL + sheet_id
        assert isinstance(result, dict)
        assert result["sheet_id"] == "sheet-target-789"
        assert "url" in result
        assert "sheet-target-789" in result["url"]
        assert result["url"].startswith("https://docs.google.com/spreadsheets/")

    def test_populate_vendor_form_raises_when_template_id_missing(self, monkeypatch):
        """If SHEETS_VENDOR_TEMPLATE_ID is unset, populate_vendor_form must raise RuntimeError."""
        # Arrange
        monkeypatch.delenv("SHEETS_VENDOR_TEMPLATE_ID", raising=False)
        mock_service = self._build_mock_service()

        with patch("orchestra_tprm.adapters.sheets.google_auth_default") as mock_auth, \
             patch("orchestra_tprm.adapters.sheets.build") as mock_build:
            mock_auth.return_value = (MagicMock(), "p")
            mock_build.return_value = mock_service
            adapter = SheetsAdapter()

            # Act / Assert
            with pytest.raises(RuntimeError, match="SHEETS_VENDOR_TEMPLATE_ID"):
                adapter.populate_vendor_form("sheet-target", {"vendor_name": "X"})

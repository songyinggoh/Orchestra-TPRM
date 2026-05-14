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
)
from orchestra_tprm.adapters.drive import DriveAdapter


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
# DriveAdapter (real) Tests — service client is mocked
# ---------------------------------------------------------------------------

class TestDriveAdapterReal:
    """Real DriveAdapter wraps google-api-python-client Drive v3 with ADC.

    All tests mock the underlying service client — no live API.
    """

    def _build_mock_service(self, files_payload: list[dict] | None = None) -> MagicMock:
        """Construct a chainable MagicMock matching the googleapiclient surface."""
        service = MagicMock(name="drive_service")
        files_resource = MagicMock(name="files_resource")
        list_request = MagicMock(name="list_request")
        list_request.execute.return_value = {"files": files_payload or []}
        files_resource.list.return_value = list_request
        service.files.return_value = files_resource
        return service

    def test_init_does_not_call_google_apis(self):
        """Constructor must be lazy — no auth or HTTP at __init__ time."""
        # If `google.auth.default` were called eagerly, instantiation would
        # require ADC credentials in the test environment. Lazy init means
        # the test can construct DriveAdapter() with no patches.
        with patch("google.auth.default") as mock_default, \
             patch("googleapiclient.discovery.build") as mock_build:
            adapter = DriveAdapter()
            assert adapter is not None
            mock_default.assert_not_called()
            mock_build.assert_not_called()

    def test_list_files_returns_list_of_dicts(self):
        """list_files must return the 'files' array from Drive's v3 response."""
        adapter = DriveAdapter()
        mock_service = self._build_mock_service([
            {"id": "f1", "name": "msa.pdf", "mimeType": "application/pdf"},
            {"id": "f2", "name": "soc2.pdf", "mimeType": "application/pdf"},
        ])

        with patch.object(adapter, "_get_service", return_value=mock_service):
            result = adapter.list_files("folder_abc")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "f1"
        assert result[0]["name"] == "msa.pdf"

    def test_list_files_filters_by_folder_id_and_excludes_trashed(self):
        """The Drive query must scope to parent folder and exclude trashed files."""
        adapter = DriveAdapter()
        mock_service = self._build_mock_service([])

        with patch.object(adapter, "_get_service", return_value=mock_service):
            adapter.list_files("my_folder_123")

        # Inspect the kwargs passed to .files().list(...)
        files_resource = mock_service.files.return_value
        call_kwargs = files_resource.list.call_args.kwargs
        assert "my_folder_123" in call_kwargs["q"]
        assert "in parents" in call_kwargs["q"]
        assert "trashed = false" in call_kwargs["q"]

    def test_list_files_requests_metadata_only_fields(self):
        """Adapter must NOT download blobs — only request metadata fields."""
        adapter = DriveAdapter()
        mock_service = self._build_mock_service([])

        with patch.object(adapter, "_get_service", return_value=mock_service):
            adapter.list_files("any_folder")

        files_resource = mock_service.files.return_value
        call_kwargs = files_resource.list.call_args.kwargs
        # Must request metadata fields, must NOT contain anything implying blob download
        assert "files(" in call_kwargs["fields"]
        assert "id" in call_kwargs["fields"]
        assert "name" in call_kwargs["fields"]

    def test_list_files_unknown_folder_returns_empty_list(self):
        """Empty 'files' array from Drive must surface as []."""
        adapter = DriveAdapter()
        mock_service = self._build_mock_service([])

        with patch.object(adapter, "_get_service", return_value=mock_service):
            result = adapter.list_files("nonexistent_folder")

        assert result == []

    def test_list_files_missing_files_key_returns_empty_list(self):
        """If the Drive response omits 'files', adapter must default to []."""
        adapter = DriveAdapter()
        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.return_value = {}

        with patch.object(adapter, "_get_service", return_value=mock_service):
            result = adapter.list_files("some_folder")

        assert result == []

    def test_get_service_uses_adc_and_builds_drive_v3(self):
        """_get_service must call google.auth.default and build drive v3."""
        adapter = DriveAdapter()
        fake_creds = MagicMock(name="creds")
        fake_service = MagicMock(name="service")

        with patch("google.auth.default", return_value=(fake_creds, "proj")) as mock_default, \
             patch("googleapiclient.discovery.build", return_value=fake_service) as mock_build:
            svc = adapter._get_service()

        assert svc is fake_service
        mock_default.assert_called_once()
        mock_build.assert_called_once()
        # Positional args: ("drive", "v3"); credentials must be passed through
        build_args, build_kwargs = mock_build.call_args
        assert build_args[0] == "drive"
        assert build_args[1] == "v3"
        assert build_kwargs["credentials"] is fake_creds

    def test_get_service_is_cached_across_calls(self):
        """_get_service must memoize — only authenticate/build once per adapter."""
        adapter = DriveAdapter()
        fake_creds = MagicMock()
        fake_service = MagicMock()

        with patch("google.auth.default", return_value=(fake_creds, "p")) as mock_default, \
             patch("googleapiclient.discovery.build", return_value=fake_service) as mock_build:
            svc1 = adapter._get_service()
            svc2 = adapter._get_service()

        assert svc1 is svc2
        assert mock_default.call_count == 1
        assert mock_build.call_count == 1

    def test_custom_scopes_are_respected(self):
        """Caller may override OAuth scopes via constructor."""
        custom = ["https://www.googleapis.com/auth/drive.readonly"]
        adapter = DriveAdapter(scopes=custom)
        fake_creds = MagicMock()

        with patch("google.auth.default", return_value=(fake_creds, "p")) as mock_default, \
             patch("googleapiclient.discovery.build", return_value=MagicMock()):
            adapter._get_service()

        scopes_arg = mock_default.call_args.kwargs.get("scopes") or mock_default.call_args.args[0]
        assert scopes_arg == custom

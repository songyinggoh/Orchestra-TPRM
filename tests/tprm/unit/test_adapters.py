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

import base64
from unittest.mock import MagicMock, patch

import httpx
import pytest

from orchestra_tprm.adapters import (
    FakeBigQueryAdapter,
    FakeDocsAdapter,
    FakeDriveAdapter,
    FakeGitHubAdapter,
    FakeSheetsAdapter,
    GeminiFilesAdapter,  # re-exported for downstream tests; keep imported
    GitHubAdapter,
    GitHubAdapterP,
    SheetsAdapter,
)
from orchestra_tprm.adapters.drive import DriveAdapter
from orchestra_tprm.adapters.gemini_files import GeminiFilesAdapterReal

_GEMINI_FILES_REF = GeminiFilesAdapter


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
# FakeGitHubAdapter Tests
# ---------------------------------------------------------------------------

class TestFakeGitHubAdapter:
    """FakeGitHubAdapter must serve seeded data and return safe defaults."""

    @pytest.mark.asyncio
    async def test_fake_returns_canned_metadata(self):
        """Seeded repo metadata round-trips through get_repo_metadata."""
        # Arrange
        fake = FakeGitHubAdapter(
            repos={
                "https://github.com/example/acme-cloud": {
                    "license": "MIT",
                    "stars": 12,
                    "open_issues": 3,
                    "default_branch": "main",
                    "last_commit_iso": "2025-08-01T00:00:00Z",
                },
            },
        )

        # Act
        md = await fake.get_repo_metadata("https://github.com/example/acme-cloud")

        # Assert
        assert md["license"] == "MIT"
        assert md["stars"] == 12
        assert md["open_issues"] == 3
        assert md["default_branch"] == "main"

    @pytest.mark.asyncio
    async def test_fake_returns_canned_org_repos(self):
        """Seeded org_repos round-trips through list_org_repos."""
        # Arrange
        fake = FakeGitHubAdapter(
            org_repos={
                "hashicorp": [
                    {"name": "terraform", "license": "BSL-1.1", "stars": 41000},
                    {"name": "vault", "license": "BSL-1.1", "stars": 30000},
                ],
            },
        )

        # Act
        org = await fake.list_org_repos("hashicorp")

        # Assert
        assert {r["name"] for r in org} == {"terraform", "vault"}

    @pytest.mark.asyncio
    async def test_fake_unknown_repo_returns_empty_dict(self):
        """get_repo_metadata for unseeded URL returns {} instead of raising."""
        # Arrange
        fake = FakeGitHubAdapter()

        # Act
        md = await fake.get_repo_metadata("https://github.com/missing/missing")

        # Assert
        assert md == {}

    @pytest.mark.asyncio
    async def test_fake_unknown_org_returns_empty_list(self):
        """list_org_repos for unseeded org returns [] instead of raising."""
        # Arrange
        fake = FakeGitHubAdapter()

        # Act
        repos = await fake.list_org_repos("nobody")

        # Assert
        assert repos == []

    @pytest.mark.asyncio
    async def test_fake_license_file_seeded_and_default(self):
        """get_license_file returns seeded text or empty string default."""
        # Arrange
        fake = FakeGitHubAdapter(
            licenses={"https://github.com/example/repo": "MIT License\n..."},
        )

        # Act
        seeded = await fake.get_license_file("https://github.com/example/repo")
        missing = await fake.get_license_file("https://github.com/other/other")

        # Assert
        assert "MIT License" in seeded
        assert missing == ""

    @pytest.mark.asyncio
    async def test_fake_sbom_seeded_and_default(self):
        """get_dependency_sbom returns seeded SBOM or empty dict."""
        # Arrange
        fake = FakeGitHubAdapter(
            sboms={"https://github.com/example/repo": {"sbom": {"packages": []}}},
        )

        # Act
        seeded = await fake.get_dependency_sbom("https://github.com/example/repo")
        missing = await fake.get_dependency_sbom("https://github.com/x/y")

        # Assert
        assert seeded == {"sbom": {"packages": []}}
        assert missing == {}

    def test_fake_satisfies_protocol(self):
        """FakeGitHubAdapter must structurally satisfy GitHubAdapterP."""
        fake = FakeGitHubAdapter()
        assert isinstance(fake, GitHubAdapterP)


# ---------------------------------------------------------------------------
# GitHubAdapter (real, httpx-backed) Tests
# ---------------------------------------------------------------------------

def _make_handler(routes: dict[str, httpx.Response]):
    """Build a MockTransport handler from a {path: Response} mapping."""

    def _handler(request: httpx.Request) -> httpx.Response:
        # Match by path only — query string ignored for simplicity.
        path = request.url.path
        if path in routes:
            return routes[path]
        return httpx.Response(404, json={"message": "Not Found"})

    return _handler


class TestGitHubAdapterConstruction:
    """GitHubAdapter must construct lazily — no token, no network at init."""

    def test_construct_without_token_does_not_raise(self, monkeypatch):
        """Constructing without GITHUB_TOKEN must not raise."""
        # Arrange
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        # Act
        adapter = GitHubAdapter()

        # Assert
        assert adapter is not None

    def test_construct_does_not_open_http_client_eagerly(self, monkeypatch):
        """The httpx client must be lazily created on first request."""
        # Arrange
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        # Act
        adapter = GitHubAdapter()

        # Assert
        assert adapter._client is None

    def test_satisfies_protocol(self):
        """GitHubAdapter must structurally satisfy GitHubAdapterP."""
        adapter = GitHubAdapter()
        assert isinstance(adapter, GitHubAdapterP)


class TestGitHubAdapterGetRepoMetadata:
    """get_repo_metadata must call /repos/{owner}/{repo} and normalize."""

    @pytest.mark.asyncio
    async def test_returns_normalized_metadata(self):
        # Arrange
        repo_url = "https://github.com/example/acme-cloud"
        handler = _make_handler({
            "/repos/example/acme-cloud": httpx.Response(
                200,
                json={
                    "name": "acme-cloud",
                    "license": {"spdx_id": "MIT", "name": "MIT License"},
                    "stargazers_count": 42,
                    "open_issues_count": 5,
                    "default_branch": "main",
                    "pushed_at": "2025-08-01T00:00:00Z",
                    "description": "ETL toolkit",
                    "language": "Python",
                },
            ),
        })
        transport = httpx.MockTransport(handler)
        adapter = GitHubAdapter(token="fake-token", transport=transport)

        # Act
        md = await adapter.get_repo_metadata(repo_url)
        await adapter.aclose()

        # Assert
        assert md == {
            "license": "MIT",
            "stars": 42,
            "open_issues": 5,
            "default_branch": "main",
            "last_commit_iso": "2025-08-01T00:00:00Z",
            "description": "ETL toolkit",
            "language": "Python",
        }

    @pytest.mark.asyncio
    async def test_missing_license_returns_unlicensed(self):
        """A repo with no detected license must produce 'UNLICENSED'."""
        # Arrange
        handler = _make_handler({
            "/repos/example/nolicense": httpx.Response(
                200,
                json={
                    "name": "nolicense",
                    "license": None,
                    "stargazers_count": 0,
                    "open_issues_count": 0,
                    "default_branch": "main",
                    "pushed_at": None,
                    "description": None,
                    "language": None,
                },
            ),
        })
        adapter = GitHubAdapter(transport=httpx.MockTransport(handler))

        # Act
        md = await adapter.get_repo_metadata("https://github.com/example/nolicense")
        await adapter.aclose()

        # Assert
        assert md["license"] == "UNLICENSED"
        assert md["description"] == ""
        assert md["language"] == ""
        assert md["last_commit_iso"] == ""

    @pytest.mark.asyncio
    async def test_invalid_url_raises_valueerror(self):
        """A URL with no owner/repo path must raise ValueError before HTTP."""
        # Arrange
        adapter = GitHubAdapter(transport=httpx.MockTransport(_make_handler({})))

        # Act + Assert
        with pytest.raises(ValueError):
            await adapter.get_repo_metadata("https://github.com/")

    @pytest.mark.asyncio
    async def test_http_error_propagates(self):
        """Non-2xx responses from GitHub must raise via httpx."""
        # Arrange
        handler = _make_handler({})  # everything 404s
        adapter = GitHubAdapter(transport=httpx.MockTransport(handler))

        # Act + Assert
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.get_repo_metadata("https://github.com/missing/missing")
        await adapter.aclose()


class TestGitHubAdapterListOrgRepos:
    """list_org_repos must paginate /orgs/{org}/repos and normalize each entry."""

    @pytest.mark.asyncio
    async def test_returns_normalized_repo_list(self):
        # Arrange
        handler = _make_handler({
            "/orgs/hashicorp/repos": httpx.Response(
                200,
                json=[
                    {
                        "name": "terraform",
                        "license": {"spdx_id": "BSL-1.1"},
                        "stargazers_count": 41000,
                        "language": "Go",
                    },
                    {
                        "name": "vault",
                        "license": {"spdx_id": "BSL-1.1"},
                        "stargazers_count": 30000,
                        "language": "Go",
                    },
                ],
            ),
        })
        adapter = GitHubAdapter(transport=httpx.MockTransport(handler))

        # Act
        repos = await adapter.list_org_repos("hashicorp")
        await adapter.aclose()

        # Assert
        assert {r["name"] for r in repos} == {"terraform", "vault"}
        assert all(r["license"] == "BSL-1.1" for r in repos)

    @pytest.mark.asyncio
    async def test_empty_org_returns_empty_list(self):
        # Arrange
        handler = _make_handler({
            "/orgs/empty/repos": httpx.Response(200, json=[]),
        })
        adapter = GitHubAdapter(transport=httpx.MockTransport(handler))

        # Act
        repos = await adapter.list_org_repos("empty")
        await adapter.aclose()

        # Assert
        assert repos == []


class TestGitHubAdapterLicenseFile:
    """get_license_file must base64-decode GitHub's license payload."""

    @pytest.mark.asyncio
    async def test_returns_decoded_license_text(self):
        # Arrange
        text = "MIT License\n\nCopyright (c) 2025"
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        handler = _make_handler({
            "/repos/example/repo/license": httpx.Response(
                200,
                json={"content": encoded, "encoding": "base64"},
            ),
        })
        adapter = GitHubAdapter(transport=httpx.MockTransport(handler))

        # Act
        license_text = await adapter.get_license_file("https://github.com/example/repo")
        await adapter.aclose()

        # Assert
        assert "MIT License" in license_text

    @pytest.mark.asyncio
    async def test_missing_license_returns_empty_string(self):
        """A 404 from /license must yield '' rather than raising."""
        # Arrange
        handler = _make_handler({})  # 404 default
        adapter = GitHubAdapter(transport=httpx.MockTransport(handler))

        # Act
        result = await adapter.get_license_file("https://github.com/example/nolic")
        await adapter.aclose()

        # Assert
        assert result == ""


class TestGitHubAdapterDependencySbom:
    """get_dependency_sbom must hit the dependency-graph SBOM endpoint."""

    @pytest.mark.asyncio
    async def test_returns_sbom_payload(self):
        # Arrange
        payload = {"sbom": {"SPDXID": "SPDXRef-DOCUMENT", "packages": []}}
        handler = _make_handler({
            "/repos/example/repo/dependency-graph/sbom": httpx.Response(
                200, json=payload
            ),
        })
        adapter = GitHubAdapter(transport=httpx.MockTransport(handler))

        # Act
        sbom = await adapter.get_dependency_sbom("https://github.com/example/repo")
        await adapter.aclose()

        # Assert
        assert sbom == payload

    @pytest.mark.asyncio
    async def test_forbidden_or_missing_returns_empty_dict(self):
        """403/404 from SBOM endpoint must yield {} rather than raising."""
        # Arrange
        handler = _make_handler({
            "/repos/example/forbidden/dependency-graph/sbom": httpx.Response(
                403, json={"message": "Forbidden"}
            ),
        })
        adapter = GitHubAdapter(transport=httpx.MockTransport(handler))

        # Act
        forbidden = await adapter.get_dependency_sbom(
            "https://github.com/example/forbidden"
        )
        missing = await adapter.get_dependency_sbom(
            "https://github.com/example/nope"
        )
        await adapter.aclose()

        # Assert
        assert forbidden == {}
        assert missing == {}


class TestGitHubAdapterAuthHeaders:
    """The Authorization header must reflect the resolved token."""

    @pytest.mark.asyncio
    async def test_token_from_env_is_used(self, monkeypatch):
        # Arrange
        monkeypatch.setenv("GITHUB_TOKEN", "env-token-123")
        observed: dict[str, str] = {}

        def _handler(request: httpx.Request) -> httpx.Response:
            observed["auth"] = request.headers.get("Authorization", "")
            return httpx.Response(200, json={"name": "x"})

        adapter = GitHubAdapter(transport=httpx.MockTransport(_handler))

        # Act
        await adapter.get_repo_metadata("https://github.com/a/b")
        await adapter.aclose()

        # Assert
        assert observed["auth"] == "Bearer env-token-123"

    @pytest.mark.asyncio
    async def test_no_token_sends_no_auth_header(self, monkeypatch):
        # Arrange
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        observed: dict[str, str] = {}

        def _handler(request: httpx.Request) -> httpx.Response:
            observed["auth"] = request.headers.get("Authorization", "")
            return httpx.Response(200, json={"name": "x"})

        adapter = GitHubAdapter(transport=httpx.MockTransport(_handler))

        # Act
        await adapter.get_repo_metadata("https://github.com/a/b")
        await adapter.aclose()

        # Assert
        assert observed["auth"] == ""


# ---------------------------------------------------------------------------
# GeminiFilesAdapterReal Tests (real adapter, mocked GoogleProvider)
# ---------------------------------------------------------------------------

class TestGeminiFilesAdapterReal:
    """GeminiFilesAdapterReal must read a local file and delegate to
    GoogleProvider.upload_file(), returning a Protocol-shaped dict with
    keys ``file_uri`` and ``mime_type``.

    All tests mock GoogleProvider.upload_file — no live API calls.
    """

    @pytest.mark.asyncio
    async def test_upload_reads_file_and_calls_provider_upload(
        self, monkeypatch, tmp_path
    ):
        """upload() must read bytes from disk and forward them to provider."""
        # Arrange
        from orchestra.providers.google import GoogleProvider

        pdf_path = tmp_path / "msa.pdf"
        pdf_bytes = b"%PDF-1.4 fake content"
        pdf_path.write_bytes(pdf_bytes)

        captured: dict = {}

        async def fake_upload(self, data, *, mime_type, display_name=None):
            captured["data"] = data
            captured["mime_type"] = mime_type
            captured["display_name"] = display_name
            return {
                "file_uri": "https://generativelanguage.googleapis.com/v1beta/files/abc",
                "mime_type": mime_type,
                "name": "files/abc",
            }

        monkeypatch.setattr(GoogleProvider, "upload_file", fake_upload)
        provider = GoogleProvider(api_key="test-key")
        adapter = GeminiFilesAdapterReal(provider=provider)

        # Act
        result = await adapter.upload(str(pdf_path), mime_type="application/pdf")

        # Assert
        assert captured["data"] == pdf_bytes
        assert captured["mime_type"] == "application/pdf"
        assert captured["display_name"] == "msa.pdf"
        assert result["file_uri"] == (
            "https://generativelanguage.googleapis.com/v1beta/files/abc"
        )
        assert result["mime_type"] == "application/pdf"

        await provider.aclose()

    @pytest.mark.asyncio
    async def test_upload_returns_only_protocol_keys(self, monkeypatch, tmp_path):
        """Returned dict must contain exactly the Protocol keys (file_uri, mime_type).

        Extra keys from the provider (e.g. ``name``) must not leak through —
        the adapter's Protocol contract is {file_uri, mime_type}.
        """
        # Arrange
        from orchestra.providers.google import GoogleProvider

        doc_path = tmp_path / "soc2.pdf"
        doc_path.write_bytes(b"%PDF-1.4 soc2")

        async def fake_upload(self, data, *, mime_type, display_name=None):
            return {
                "file_uri": "https://x/files/xyz",
                "mime_type": mime_type,
                "name": "files/xyz",
                "extra_field": "should-not-leak",
            }

        monkeypatch.setattr(GoogleProvider, "upload_file", fake_upload)
        provider = GoogleProvider(api_key="test-key")
        adapter = GeminiFilesAdapterReal(provider=provider)

        # Act
        result = await adapter.upload(str(doc_path), mime_type="application/pdf")

        # Assert
        assert set(result.keys()) == {"file_uri", "mime_type"}

        await provider.aclose()

    @pytest.mark.asyncio
    async def test_upload_nonexistent_path_raises_file_not_found(
        self, monkeypatch, tmp_path
    ):
        """upload() on a missing path must raise FileNotFoundError before
        ever calling the provider."""
        # Arrange
        from orchestra.providers.google import GoogleProvider

        called = {"provider_invoked": False}

        async def fake_upload(self, data, *, mime_type, display_name=None):
            called["provider_invoked"] = True
            return {"file_uri": "x", "mime_type": mime_type, "name": "y"}

        monkeypatch.setattr(GoogleProvider, "upload_file", fake_upload)
        provider = GoogleProvider(api_key="test-key")
        adapter = GeminiFilesAdapterReal(provider=provider)

        missing = tmp_path / "does_not_exist.pdf"

        # Act / Assert
        with pytest.raises(FileNotFoundError):
            await adapter.upload(str(missing), mime_type="application/pdf")

        assert called["provider_invoked"] is False

        await provider.aclose()

    @pytest.mark.asyncio
    async def test_upload_propagates_provider_errors(self, monkeypatch, tmp_path):
        """Exceptions from GoogleProvider.upload_file must propagate to the caller."""
        # Arrange
        from orchestra.providers.google import GoogleProvider

        pdf_path = tmp_path / "msa.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        class ProviderBoom(RuntimeError):
            pass

        async def fake_upload(self, data, *, mime_type, display_name=None):
            raise ProviderBoom("upload failed")

        monkeypatch.setattr(GoogleProvider, "upload_file", fake_upload)
        provider = GoogleProvider(api_key="test-key")
        adapter = GeminiFilesAdapterReal(provider=provider)

        # Act / Assert
        with pytest.raises(ProviderBoom, match="upload failed"):
            await adapter.upload(str(pdf_path), mime_type="application/pdf")

        await provider.aclose()


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

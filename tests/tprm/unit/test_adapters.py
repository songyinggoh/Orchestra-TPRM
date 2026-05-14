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
)

# Reference GeminiFilesAdapter so ruff F401 sees a use — the placeholder
# tests below only have `pass` bodies, so the class itself is not yet
# exercised, but the import is intentional surface-area validation.
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

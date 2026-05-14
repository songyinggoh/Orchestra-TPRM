from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from orchestra_tprm.adapters.bigquery import FakeBigQueryAdapter
from orchestra_tprm.adapters.docs import FakeDocsAdapter
from orchestra_tprm.adapters.drive import FakeDriveAdapter
from orchestra_tprm.adapters.gemini_files import GeminiFilesAdapter
from orchestra_tprm.adapters.github import FakeGitHubAdapter, GitHubAdapter
from orchestra_tprm.adapters.sheets import FakeSheetsAdapter


@runtime_checkable
class GitHubAdapterP(Protocol):
    """Structural protocol for GitHub-adapter implementations.

    Both ``GitHubAdapter`` (real, httpx-backed) and ``FakeGitHubAdapter``
    (in-memory) satisfy this protocol. CodeAgent (Task 27) depends on it.
    """

    async def get_repo_metadata(self, repo_url: str) -> dict[str, Any]: ...
    async def list_org_repos(self, org: str) -> list[dict[str, Any]]: ...
    async def get_license_file(self, repo_url: str) -> str: ...
    async def get_dependency_sbom(self, repo_url: str) -> dict[str, Any]: ...


__all__ = [
    "FakeBigQueryAdapter",
    "FakeDocsAdapter",
    "FakeDriveAdapter",
    "FakeGitHubAdapter",
    "FakeSheetsAdapter",
    "GeminiFilesAdapter",
    "GitHubAdapter",
    "GitHubAdapterP",
]

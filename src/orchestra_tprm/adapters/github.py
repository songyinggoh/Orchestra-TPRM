"""GitHubAdapter — async httpx wrapper around the GitHub REST v3 API.

Used by ``CodeAgent`` (vendor-mode license audit) and other TPRM
specialists that need repository metadata, license files, or dependency
manifests for the vendor's open-source code.

Design notes:
    * The httpx client is built lazily so unit tests can instantiate
      ``GitHubAdapter()`` without a token and without network I/O.
    * ``GITHUB_TOKEN`` is read from the environment but is OPTIONAL —
      anonymous calls work (subject to GitHub's rate limits).
    * All methods are ``async`` and return JSON-shaped ``dict`` / ``list``
      results so they can be swapped 1:1 with ``FakeGitHubAdapter`` in
      unit tests.
"""
from __future__ import annotations

import base64
import os
from typing import Any
from urllib.parse import urlparse

import httpx

_GITHUB_API_BASE = "https://api.github.com"


def _parse_owner_repo(url: str) -> tuple[str, str]:
    """Parse ``https://github.com/<owner>/<repo>`` into ``(owner, repo)``."""
    p = urlparse(url)
    parts = [s for s in p.path.split("/") if s]
    if len(parts) >= 2:
        # Strip trailing ``.git`` if present.
        repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
        return parts[0], repo
    raise ValueError(f"Cannot parse owner/repo from {url!r}")


class GitHubAdapter:
    """Real GitHub REST v3 adapter (async, httpx-backed).

    Args:
        token: GitHub personal-access token. Defaults to ``GITHUB_TOKEN``
            env at first network call. Absence is non-fatal — unit tests
            construct without a token.
        transport: Optional ``httpx.BaseTransport`` (e.g. ``MockTransport``
            or a ``respx`` router) for testing.
        base_url: Override the GitHub API base (useful for GHES).
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        base_url: str = _GITHUB_API_BASE,
        timeout: float = 30.0,
    ) -> None:
        self._explicit_token = token
        self._transport = transport
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------
    def _resolve_token(self) -> str:
        if self._explicit_token is not None:
            return self._explicit_token
        return os.environ.get("GITHUB_TOKEN", "")

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            token = self._resolve_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                transport=self._transport,
                timeout=self._timeout,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def get_repo_metadata(self, repo_url: str) -> dict[str, Any]:
        """Return normalized metadata for a single repository."""
        owner, repo = _parse_owner_repo(repo_url)
        client = self._get_client()
        resp = await client.get(f"/repos/{owner}/{repo}")
        resp.raise_for_status()
        data = resp.json()
        license_obj = data.get("license") or {}
        return {
            "license": license_obj.get("spdx_id") or "UNLICENSED",
            "stars": data.get("stargazers_count", 0),
            "open_issues": data.get("open_issues_count", 0),
            "default_branch": data.get("default_branch", ""),
            "last_commit_iso": data.get("pushed_at", "") or "",
            "description": data.get("description") or "",
            "language": data.get("language") or "",
        }

    async def list_org_repos(self, org: str) -> list[dict[str, Any]]:
        """List all repos for an org (paginated, normalized)."""
        client = self._get_client()
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = await client.get(
                f"/orgs/{org}/repos",
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            chunk = resp.json()
            if not chunk:
                break
            for r in chunk:
                license_obj = r.get("license") or {}
                out.append(
                    {
                        "name": r.get("name", ""),
                        "license": license_obj.get("spdx_id") or "UNLICENSED",
                        "stars": r.get("stargazers_count", 0),
                        "language": r.get("language") or "",
                    }
                )
            if len(chunk) < 100:
                break
            page += 1
        return out

    async def get_license_file(self, repo_url: str) -> str:
        """Return the full text of the repo's LICENSE file (UTF-8 decoded).

        Returns an empty string if the repo has no detectable license file.
        """
        owner, repo = _parse_owner_repo(repo_url)
        client = self._get_client()
        resp = await client.get(f"/repos/{owner}/{repo}/license")
        if resp.status_code == 404:
            return ""
        resp.raise_for_status()
        payload = resp.json()
        content_b64 = payload.get("content", "")
        encoding = payload.get("encoding", "base64")
        if not content_b64:
            return ""
        if encoding == "base64":
            try:
                return base64.b64decode(content_b64).decode("utf-8", errors="replace")
            except (ValueError, TypeError):
                return ""
        return str(content_b64)

    async def get_dependency_sbom(self, repo_url: str) -> dict[str, Any]:
        """Fetch the SPDX SBOM for the repo via GitHub's dependency-graph API.

        Returns an empty dict if the endpoint is unavailable (e.g. private
        repo without permission, or SBOM not yet generated).
        """
        owner, repo = _parse_owner_repo(repo_url)
        client = self._get_client()
        resp = await client.get(f"/repos/{owner}/{repo}/dependency-graph/sbom")
        if resp.status_code in (403, 404):
            return {}
        resp.raise_for_status()
        return resp.json()


class FakeGitHubAdapter:
    """In-memory fake for unit testing GitHub-consuming agents.

    Seeded via ``repos=``, ``org_repos=``, ``licenses=``, and ``sboms=``
    keyed by ``repo_url`` (or org name for ``org_repos``).
    """

    def __init__(
        self,
        *,
        repos: dict[str, dict[str, Any]] | None = None,
        org_repos: dict[str, list[dict[str, Any]]] | None = None,
        licenses: dict[str, str] | None = None,
        sboms: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._repos = repos or {}
        self._org_repos = org_repos or {}
        self._licenses = licenses or {}
        self._sboms = sboms or {}

    async def get_repo_metadata(self, repo_url: str) -> dict[str, Any]:
        return dict(self._repos.get(repo_url, {}))

    async def list_org_repos(self, org: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self._org_repos.get(org, [])]

    async def get_license_file(self, repo_url: str) -> str:
        return self._licenses.get(repo_url, "")

    async def get_dependency_sbom(self, repo_url: str) -> dict[str, Any]:
        return dict(self._sboms.get(repo_url, {}))

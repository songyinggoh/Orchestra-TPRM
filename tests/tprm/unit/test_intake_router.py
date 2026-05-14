"""Unit tests for IntakeAgent and DocRouterAgent.

No live API calls, no Postgres, no real Drive/Gemini.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from orchestra.core.context import ExecutionContext
from orchestra.testing import ScriptedLLM
from orchestra_tprm.agents.intake import IntakeAgent
from orchestra_tprm.agents.router import DocRouterAgent


# ---------------------------------------------------------------------------
# Minimal in-test stubs (per constraint 4: no modifications to drive.py)
# ---------------------------------------------------------------------------


class LocalFakeDriveAdapter:
    """Minimal drive stub for tests — returns seeded metadata lists."""

    def __init__(self) -> None:
        self._folders: dict[str, list[dict]] = {}
        self._files: dict[str, bytes] = {}

    def seed_folder(
        self,
        folder_id: str,
        files: list[dict],
        contents: dict[str, bytes] | None = None,
    ) -> None:
        self._folders[folder_id] = files
        if contents:
            self._files.update(contents)

    def list_files(self, folder_id: str) -> list[dict]:
        return list(self._folders.get(folder_id, []))

    def download_file(self, file_id: str) -> bytes:
        return self._files.get(file_id, b"")


class FakeGeminiFilesAdapter:
    """In-memory fake that records uploads and returns predictable URIs."""

    def __init__(self) -> None:
        self.uploaded: list[tuple[str, str]] = []  # (file_id, mime_type)

    async def upload(self, file_id: str, mime_type: str) -> dict[str, str]:
        self.uploaded.append((file_id, mime_type))
        uri = f"gemini://files/{file_id}"
        return {"file_uri": uri, "mime_type": mime_type}


# ---------------------------------------------------------------------------
# IntakeAgent tests
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_drive() -> LocalFakeDriveAdapter:
    drive = LocalFakeDriveAdapter()
    drive.seed_folder(
        "folder-abc",
        [
            {"id": "file-1", "name": "MSA_2024.pdf", "mimeType": "application/pdf"},
            {"id": "file-2", "name": "SOC2_2024.pdf", "mimeType": "application/pdf"},
        ],
        {
            "file-1": b"%PDF-1.4 fake-msa",
            "file-2": b"%PDF-1.4 fake-soc2",
        },
    )
    return drive


@pytest.fixture
def fake_gemini() -> FakeGeminiFilesAdapter:
    return FakeGeminiFilesAdapter()


class TestIntakeAgent:
    """IntakeAgent should list files from Drive and upload each to Gemini."""

    @pytest.mark.asyncio
    async def test_run_returns_manifest(
        self,
        sample_drive: LocalFakeDriveAdapter,
        fake_gemini: FakeGeminiFilesAdapter,
    ) -> None:
        agent = IntakeAgent(
            drive_adapter=sample_drive,
            gemini_files_adapter=fake_gemini,
            folder_id="folder-abc",
        )
        manifest = await agent.process()

        assert len(manifest) == 2

    @pytest.mark.asyncio
    async def test_manifest_has_required_keys(
        self,
        sample_drive: LocalFakeDriveAdapter,
        fake_gemini: FakeGeminiFilesAdapter,
    ) -> None:
        agent = IntakeAgent(
            drive_adapter=sample_drive,
            gemini_files_adapter=fake_gemini,
            folder_id="folder-abc",
        )
        manifest = await agent.process()

        for entry in manifest:
            assert "file_uri" in entry
            assert "mime_type" in entry
            assert "name" in entry

    @pytest.mark.asyncio
    async def test_file_uris_correspond_to_drive_files(
        self,
        sample_drive: LocalFakeDriveAdapter,
        fake_gemini: FakeGeminiFilesAdapter,
    ) -> None:
        agent = IntakeAgent(
            drive_adapter=sample_drive,
            gemini_files_adapter=fake_gemini,
            folder_id="folder-abc",
        )
        manifest = await agent.process()

        uris = {entry["file_uri"] for entry in manifest}
        assert "gemini://files/file-1" in uris
        assert "gemini://files/file-2" in uris

    @pytest.mark.asyncio
    async def test_manifest_names_match_drive_filenames(
        self,
        sample_drive: LocalFakeDriveAdapter,
        fake_gemini: FakeGeminiFilesAdapter,
    ) -> None:
        agent = IntakeAgent(
            drive_adapter=sample_drive,
            gemini_files_adapter=fake_gemini,
            folder_id="folder-abc",
        )
        manifest = await agent.process()

        names = {entry["name"] for entry in manifest}
        assert names == {"MSA_2024.pdf", "SOC2_2024.pdf"}

    @pytest.mark.asyncio
    async def test_empty_folder_returns_empty_manifest(
        self,
        fake_gemini: FakeGeminiFilesAdapter,
    ) -> None:
        drive = LocalFakeDriveAdapter()
        drive.seed_folder("empty-folder", [])
        agent = IntakeAgent(
            drive_adapter=drive,
            gemini_files_adapter=fake_gemini,
            folder_id="empty-folder",
        )
        manifest = await agent.process()

        assert manifest == []
        assert fake_gemini.uploaded == []

    @pytest.mark.asyncio
    async def test_each_file_uploaded_to_gemini(
        self,
        sample_drive: LocalFakeDriveAdapter,
        fake_gemini: FakeGeminiFilesAdapter,
    ) -> None:
        agent = IntakeAgent(
            drive_adapter=sample_drive,
            gemini_files_adapter=fake_gemini,
            folder_id="folder-abc",
        )
        await agent.process()

        uploaded_ids = {file_id for file_id, _ in fake_gemini.uploaded}
        assert "file-1" in uploaded_ids
        assert "file-2" in uploaded_ids

    @pytest.mark.asyncio
    async def test_run_returns_same_manifest(
        self,
        sample_drive: LocalFakeDriveAdapter,
        fake_gemini: FakeGeminiFilesAdapter,
    ) -> None:
        """IntakeAgent.run() (BaseTPRMAgent compat) is not required but process()
        must work. This test verifies process() is callable stand-alone."""
        agent = IntakeAgent(
            drive_adapter=sample_drive,
            gemini_files_adapter=fake_gemini,
            folder_id="folder-abc",
        )
        manifest = await agent.process()
        assert isinstance(manifest, list)

    @pytest.mark.asyncio
    async def test_no_llm_call_made(
        self,
        sample_drive: LocalFakeDriveAdapter,
        fake_gemini: FakeGeminiFilesAdapter,
    ) -> None:
        """IntakeAgent is pure orchestration — it must NOT call an LLM."""
        llm = ScriptedLLM([])
        agent = IntakeAgent(
            drive_adapter=sample_drive,
            gemini_files_adapter=fake_gemini,
            folder_id="folder-abc",
        )
        ctx = ExecutionContext(provider=llm)
        manifest = await agent.process()

        assert llm.call_count == 0
        assert len(manifest) == 2


# ---------------------------------------------------------------------------
# DocRouterAgent tests
# ---------------------------------------------------------------------------


class TestDocRouterAgent:
    """DocRouterAgent classifies documents via LLM (Flash mock)."""

    def _make_manifest(self) -> list[dict]:
        return [
            {
                "file_uri": "gemini://files/file-1",
                "mime_type": "application/pdf",
                "name": "MSA_2024.pdf",
            },
            {
                "file_uri": "gemini://files/file-2",
                "mime_type": "application/pdf",
                "name": "SOC2_2024.pdf",
            },
        ]

    @pytest.mark.asyncio
    async def test_returns_dict_mapping_uri_to_type(self) -> None:
        """Each file_uri in the manifest maps to a document type string."""
        llm = ScriptedLLM(["CONTRACT", "SOC2"])
        agent = DocRouterAgent(manifest=self._make_manifest())
        ctx = ExecutionContext(provider=llm)

        result = await agent.classify(ctx)

        assert isinstance(result, dict)
        assert set(result.keys()) == {
            "gemini://files/file-1",
            "gemini://files/file-2",
        }

    @pytest.mark.asyncio
    async def test_known_categories_returned(self) -> None:
        """Values must be one of the five recognised document types."""
        valid = {"CONTRACT", "SOC2", "FINANCIAL", "CODE_SBOM", "OTHER"}
        llm = ScriptedLLM(["CONTRACT", "SOC2"])
        agent = DocRouterAgent(manifest=self._make_manifest())
        ctx = ExecutionContext(provider=llm)

        result = await agent.classify(ctx)

        for v in result.values():
            assert v in valid, f"Unexpected doc type: {v!r}"

    @pytest.mark.asyncio
    async def test_llm_called_once_per_document(self) -> None:
        """One LLM call per file in the manifest."""
        manifest = self._make_manifest()
        llm = ScriptedLLM(["CONTRACT", "SOC2"])
        agent = DocRouterAgent(manifest=manifest)
        ctx = ExecutionContext(provider=llm)

        await agent.classify(ctx)

        assert llm.call_count == len(manifest)

    @pytest.mark.asyncio
    async def test_unknown_llm_response_mapped_to_other(self) -> None:
        """Garbage LLM output is normalised to OTHER."""
        llm = ScriptedLLM(["DEFINITELY_NOT_A_VALID_TYPE", "SOC2"])
        agent = DocRouterAgent(manifest=self._make_manifest())
        ctx = ExecutionContext(provider=llm)

        result = await agent.classify(ctx)

        assert result["gemini://files/file-1"] == "OTHER"
        assert result["gemini://files/file-2"] == "SOC2"

    @pytest.mark.asyncio
    async def test_empty_manifest_returns_empty_dict(self) -> None:
        llm = ScriptedLLM([])
        agent = DocRouterAgent(manifest=[])
        ctx = ExecutionContext(provider=llm)

        result = await agent.classify(ctx)

        assert result == {}
        assert llm.call_count == 0

    @pytest.mark.asyncio
    async def test_llm_response_is_case_insensitive(self) -> None:
        """Lower-case or mixed-case LLM responses are normalised."""
        llm = ScriptedLLM(["contract", "Financial"])
        agent = DocRouterAgent(manifest=self._make_manifest())
        ctx = ExecutionContext(provider=llm)

        result = await agent.classify(ctx)

        assert result["gemini://files/file-1"] == "CONTRACT"
        assert result["gemini://files/file-2"] == "FINANCIAL"

    @pytest.mark.asyncio
    async def test_all_five_types_accepted(self) -> None:
        """All five document types are valid outputs."""
        valid_types = ["CONTRACT", "SOC2", "FINANCIAL", "CODE_SBOM", "OTHER"]
        manifest = [
            {
                "file_uri": f"gemini://files/file-{i}",
                "mime_type": "application/pdf",
                "name": f"doc-{i}.pdf",
            }
            for i in range(5)
        ]
        llm = ScriptedLLM(valid_types)
        agent = DocRouterAgent(manifest=manifest)
        ctx = ExecutionContext(provider=llm)

        result = await agent.classify(ctx)

        for i, uri in enumerate(f"gemini://files/file-{i}" for i in range(5)):
            assert result[uri] == valid_types[i]

    @pytest.mark.asyncio
    async def test_prompt_includes_document_name(self) -> None:
        """The LLM prompt must mention the document name for context."""
        llm = ScriptedLLM(["CONTRACT", "SOC2"])
        agent = DocRouterAgent(manifest=self._make_manifest())
        ctx = ExecutionContext(provider=llm)

        await agent.classify(ctx)

        llm.assert_prompt_received(0, r"MSA_2024")
        llm.assert_prompt_received(1, r"SOC2_2024")

    @pytest.mark.asyncio
    async def test_uses_flash_model(self) -> None:
        """DocRouterAgent must use gemini-2.5-flash (cost efficiency)."""
        llm = ScriptedLLM(["CONTRACT", "SOC2"])
        agent = DocRouterAgent(manifest=self._make_manifest())
        ctx = ExecutionContext(provider=llm)

        await agent.classify(ctx)

        for call in llm.call_log:
            assert call["model"] == "gemini-2.5-flash", (
                f"Expected gemini-2.5-flash, got {call['model']!r}"
            )

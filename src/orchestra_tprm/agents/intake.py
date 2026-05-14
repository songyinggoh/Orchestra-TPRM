"""IntakeAgent — lists files from a Drive folder and uploads each to the
Gemini Files API, producing a document manifest.

This is a pure orchestration agent: it performs no LLM call.  It composes
a DriveAdapter (sync) and a GeminiFilesAdapter (async) without importing
protocols or referencing concrete adapter classes, satisfying constraint 1
(no adapters/protocols.py) and constraint 3 (sync list_files).

Usage::

    from orchestra_tprm.agents.intake import IntakeAgent
    from orchestra_tprm.adapters.drive import FakeDriveAdapter
    from orchestra_tprm.adapters.gemini_files import GeminiFilesAdapterReal

    agent = IntakeAgent(
        drive_adapter=drive,
        gemini_files_adapter=gemini,
        folder_id="0AKxxxxxxxxxxxxUk9PVA",
    )
    manifest = await agent.process()
    # manifest: list[{"file_uri": str, "mime_type": str, "name": str}]
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MIME = "application/octet-stream"


class IntakeAgent:
    """Lists Drive folder contents and uploads each file to Gemini Files API.

    No LLM call is made — this is a pure data-pipeline agent.

    Args:
        drive_adapter: Any object with a sync ``list_files(folder_id) ->
            list[dict]`` method (FakeDriveAdapter or DriveAdapter).
        gemini_files_adapter: Any object with an async ``upload(file_id,
            mime_type) -> {"file_uri": str, "mime_type": str}`` method.
        folder_id: Google Drive folder ID to enumerate.

    Constraints honoured:
        - list_files() is called synchronously (constraint 3).
        - No import of DriveAdapterP / GeminiFilesAdapterP (constraint 1).
        - No DB / Postgres import (constraint 2).
    """

    name: str = "IntakeAgent"

    def __init__(
        self,
        *,
        drive_adapter: Any,
        gemini_files_adapter: Any,
        folder_id: str,
    ) -> None:
        self._drive = drive_adapter
        self._gemini = gemini_files_adapter
        self._folder_id = folder_id

    async def process(self) -> list[dict[str, str]]:
        """Enumerate a Drive folder and upload every file to Gemini Files API.

        Returns:
            Document manifest: a list of dicts, one per file, with keys:
                ``file_uri``  — Gemini Files URI returned by the upload.
                ``mime_type`` — MIME type of the file.
                ``name``      — Original filename from Drive metadata.
        """
        # list_files() is SYNC (constraint 3)
        files: list[dict] = self._drive.list_files(self._folder_id)

        if not files:
            logger.info("IntakeAgent: folder %r is empty", self._folder_id)
            return []

        manifest: list[dict[str, str]] = []
        for file_meta in files:
            file_id: str = file_meta.get("id", "")
            name: str = file_meta.get("name", "")
            mime_type: str = file_meta.get("mimeType", _DEFAULT_MIME)

            logger.debug(
                "IntakeAgent: uploading %r (id=%s, mime=%s)",
                name,
                file_id,
                mime_type,
            )

            # upload() is ASYNC
            result: dict[str, str] = await self._gemini.upload(file_id, mime_type)

            manifest.append(
                {
                    "file_uri": result["file_uri"],
                    "mime_type": result.get("mime_type", mime_type),
                    "name": name,
                }
            )

        logger.info(
            "IntakeAgent: processed %d file(s) from folder %r",
            len(manifest),
            self._folder_id,
        )
        return manifest

"""GeminiFilesAdapter — uploads PDFs and other binary artifacts to the
Gemini Files API for multimodal ingestion.

Two implementations live in this module:

* ``GeminiFilesAdapter`` — the existing placeholder kept in place so the
  rest of the TPRM scaffold (integration tests, conftest fixtures) can
  continue importing it. It performs no real I/O.
* ``GeminiFilesAdapterReal`` — Task 14 real adapter that reads a file
  from disk and delegates to :func:`orchestra.providers.google.GoogleProvider.upload_file`
  (landed in Task 5, commit ``e35eff1``). It conforms to the
  ``GeminiFilesAdapterP`` Protocol: ``upload(local_path, mime_type)``
  returning ``{"file_uri": str, "mime_type": str}``.

The real adapter does not own the ``GoogleProvider`` lifecycle — callers
are responsible for constructing the provider and closing it via
``provider.aclose()`` when done.
"""
from __future__ import annotations

from pathlib import Path

import aiofiles

from orchestra.providers.google import GoogleProvider


class GeminiFilesAdapter:
    """Uploads files to Gemini Files API for multimodal ingestion.
    Implemented in a later task — stub present so tests can import."""
    pass


class GeminiFilesAdapterReal:
    """Real GeminiFilesAdapter — reads bytes from disk and uploads via
    the patched :meth:`GoogleProvider.upload_file` (Task 5).

    Conforms to ``GeminiFilesAdapterP``:
        async def upload(local_path: str, mime_type: str) -> dict[str, str]

    Returned dict contains exactly ``file_uri`` and ``mime_type`` — any
    extra keys returned by the underlying provider (e.g. ``name``) are
    intentionally dropped to keep the Protocol surface tight.
    """

    def __init__(self, provider: GoogleProvider) -> None:
        self._provider = provider

    async def upload(self, local_path: str, mime_type: str) -> dict[str, str]:
        """Upload a local file to the Gemini Files API.

        Args:
            local_path: Path to the file on disk.
            mime_type: MIME type for the upload (e.g. ``application/pdf``).

        Returns:
            ``{"file_uri": "...", "mime_type": "..."}``

        Raises:
            FileNotFoundError: If ``local_path`` does not exist.
            Exception: Any error raised by :meth:`GoogleProvider.upload_file`
                propagates unchanged to the caller.
        """
        path = Path(local_path)
        if not path.is_file():
            raise FileNotFoundError(f"GeminiFilesAdapterReal: file not found: {local_path}")

        async with aiofiles.open(path, "rb") as f:
            data = await f.read()

        result = await self._provider.upload_file(
            data,
            mime_type=mime_type,
            display_name=path.name,
        )
        return {
            "file_uri": result["file_uri"],
            "mime_type": result["mime_type"],
        }

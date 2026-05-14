"""IntakeAgent — local-packet intake node.

Reads ``manifest.yaml`` from the packet directory, resolves each document
listed there, and returns state updates:

  * ``packet_manifest`` — list of ``{path, kind, file_uri}`` dicts
  * ``file_uris``        — ``{kind: file_uri}`` shorthand for specialist lookup
  * ``subject_name``    — taken from state (CLI-parsed) or manifest fallback

For the ``--local`` mode the file_uri is ``local://<absolute_path>``; no
Gemini Files API upload is performed. Live upload is deferred to Task 30
(``DriveAdapter`` + ``GeminiFilesAdapterReal``).

The function is intentionally a plain async callable so it can be wired
directly into the LangGraph / Orchestra workflow graph without subclassing
``BaseTPRMAgent`` (which is for Finding-emitting specialists only).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


async def intake_node(state: dict[str, Any]) -> dict[str, Any]:
    """Populate ``packet_manifest`` and ``file_uris`` from the local packet.

    Args:
        state: Workflow state dict.  Must contain ``packet_path`` (str or
               Path-compatible).  May contain ``subject_name`` (pre-set by
               CLI); falls back to ``subject_name`` key in ``manifest.yaml``.

    Returns:
        Partial state update dict with ``subject_name``, ``packet_manifest``,
        and ``file_uris`` keys.

    Raises:
        FileNotFoundError: If ``packet_path/manifest.yaml`` does not exist.
        yaml.YAMLError: If ``manifest.yaml`` cannot be parsed.
    """
    packet_path = Path(state.get("packet_path", ""))
    manifest_path = packet_path / "manifest.yaml"
    manifest: dict[str, Any] = yaml.safe_load(
        manifest_path.read_text(encoding="utf-8")
    )

    docs: list[dict[str, Any]] = manifest.get("docs", [])
    packet_manifest: list[dict[str, Any]] = []
    file_uris: dict[str, str] = {}

    for doc in docs:
        doc_path = packet_path / doc["path"]
        kind: str = doc.get("kind", "unknown")
        # Local path: URI carries the absolute path so downstream nodes
        # can read the file directly without network I/O.
        file_uri = f"local://{doc_path.resolve()}"
        packet_manifest.append(
            {
                "path": str(doc_path),
                "kind": kind,
                "file_uri": file_uri,
            }
        )
        # Last doc of a given kind wins; callers needing all URIs per kind
        # should iterate packet_manifest directly.
        file_uris[kind] = file_uri

    # ``subject_name`` set by CLI takes precedence; manifest is the fallback.
    subject_name: str = state.get("subject_name") or manifest.get("subject_name", "")

    return {
        "subject_name": subject_name,
        "packet_manifest": packet_manifest,
        "file_uris": file_uris,
    }

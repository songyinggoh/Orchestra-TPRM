"""URI reading utility for TPRM specialist agents.

Handles local:// URIs by stripping the prefix and reading the file from disk.
All other URI schemes return empty string (handled by GeminiFilesAdapterReal
at graph-wiring time).
"""
from __future__ import annotations

from pathlib import Path


def read_uri(uri: str) -> str:
    """Read text content from a URI.

    For ``local://`` URIs: strips the prefix and reads the file from disk.
    For all other URI schemes (https://, gs://, etc.): returns ``""`` — the
    caller is expected to pass these as multimodal attachments via the
    Gemini Files API instead.

    Args:
        uri: URI string to read from.

    Returns:
        File text for local URIs; empty string for all other schemes.
    """
    if uri.startswith("local://"):
        path = uri[len("local://"):]
        return Path(path).read_text(encoding="utf-8")
    return ""

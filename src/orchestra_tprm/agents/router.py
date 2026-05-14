"""DocRouterAgent — classifies each document in a manifest via LLM (Flash).

Accepts a list of file-metadata dicts (the output of IntakeAgent) and
returns a mapping from ``file_uri`` to one of the five recognised document
types::

    CONTRACT | SOC2 | FINANCIAL | CODE_SBOM | OTHER

LLM calls use ``gemini-2.5-flash`` (cost-efficient; no structured output
required for this classification task).  Each document is classified in its
own LLM call so the model focuses on a single file at a time.

Usage::

    from orchestra_tprm.agents.router import DocRouterAgent
    from orchestra.core.context import ExecutionContext

    agent = DocRouterAgent(manifest=manifest)
    routing = await agent.classify(ctx)
    # {"gemini://files/abc": "CONTRACT", "gemini://files/xyz": "SOC2", ...}

Constraints honoured:
    - No import of DriveAdapterP / GeminiFilesAdapterP (constraint 1).
    - No DB / Postgres import (constraint 2).
    - list_files() not called here — router receives manifest directly.
"""
from __future__ import annotations

import logging
from typing import Any

from orchestra.core.context import ExecutionContext
from orchestra.core.types import Message, MessageRole

logger = logging.getLogger(__name__)

_VALID_TYPES: frozenset[str] = frozenset(
    {"CONTRACT", "SOC2", "FINANCIAL", "CODE_SBOM", "OTHER"}
)

_MODEL = "gemini-2.5-flash"

_SYSTEM_PROMPT = (
    "You are a document classification assistant for a third-party risk "
    "management (TPRM) system. Your only task is to classify a document "
    "into exactly ONE of these five categories:\n\n"
    "  CONTRACT   — Master Service Agreements, NDAs, SLAs, and other legal "
    "agreements.\n"
    "  SOC2       — SOC 2 Type I / Type II audit reports and attestations.\n"
    "  FINANCIAL  — Financial statements, audit reports, balance sheets, "
    "income statements.\n"
    "  CODE_SBOM  — Software Bills of Materials, dependency manifests, or "
    "source-code artefacts.\n"
    "  OTHER      — Any document that does not fit the categories above.\n\n"
    "Reply with ONLY the category name — nothing else."
)


def _build_classification_prompt(name: str, mime_type: str, file_uri: str) -> str:
    return (
        f"Classify the following document.\n\n"
        f"Filename : {name}\n"
        f"MIME type: {mime_type}\n"
        f"URI      : {file_uri}\n\n"
        f"Reply with exactly one word from: CONTRACT, SOC2, FINANCIAL, "
        f"CODE_SBOM, OTHER."
    )


def _normalise(raw: str) -> str:
    """Strip whitespace, upper-case, validate; return OTHER on unknown."""
    candidate = raw.strip().upper()
    return candidate if candidate in _VALID_TYPES else "OTHER"


class DocRouterAgent:
    """Classifies documents in a manifest using an LLM (Flash).

    Args:
        manifest: List of file-metadata dicts, each with ``file_uri``,
            ``mime_type``, and ``name`` keys (output of IntakeAgent).

    Constraints honoured:
        - No import of adapter protocols (constraint 1).
        - No DB / Postgres import (constraint 2).
    """

    name: str = "DocRouterAgent"
    model: str = _MODEL

    def __init__(self, manifest: list[dict[str, Any]]) -> None:
        self._manifest = manifest

    async def classify(self, ctx: ExecutionContext) -> dict[str, str]:
        """Classify every document in the manifest via LLM.

        Args:
            ctx: ExecutionContext with an injected LLM provider.

        Returns:
            ``dict[file_uri, document_type]`` — one entry per manifest item.
        """
        if not self._manifest:
            return {}

        routing: dict[str, str] = {}

        for entry in self._manifest:
            file_uri: str = entry.get("file_uri", "")
            name: str = entry.get("name", "")
            mime_type: str = entry.get("mime_type", "application/octet-stream")

            prompt = _build_classification_prompt(name, mime_type, file_uri)

            messages = [
                Message(role=MessageRole.SYSTEM, content=_SYSTEM_PROMPT),
                Message(role=MessageRole.USER, content=prompt),
            ]

            response = await ctx.provider.complete(messages, model=self.model)
            raw_type: str = response.content or "OTHER"
            doc_type = _normalise(raw_type)

            logger.debug(
                "DocRouterAgent: %r → %s (raw=%r)", name, doc_type, raw_type
            )
            routing[file_uri] = doc_type

        logger.info(
            "DocRouterAgent: classified %d document(s)", len(routing)
        )
        return routing

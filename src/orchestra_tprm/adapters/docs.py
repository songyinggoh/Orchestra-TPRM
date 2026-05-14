"""Docs adapters — Fake (in-memory) and real Docs v1 (ADC-authenticated).

The Fake is preserved verbatim for unit/integration tests.
The real DocsAdapter authenticates via Application Default Credentials (same
pattern as SheetsAdapter) and wraps the googleapiclient Docs v1 service. It
also exposes populate_ma_memo() which writes M&A deal memo sections into the
Doc referenced by the DOCS_MA_TEMPLATE_ID env var via batchUpdate, and
returns {"doc_id", "url"}.
"""
from __future__ import annotations

import os
import uuid

# Aliased imports so unit tests can patch them at this module path.
try:  # pragma: no cover - exercised in live integration only
    from google.auth import default as google_auth_default
    from googleapiclient.discovery import build
except ImportError:  # pragma: no cover - allows import without GCP libs at runtime
    google_auth_default = None  # type: ignore[assignment]
    build = None  # type: ignore[assignment]

_DOCS_SCOPES = (
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
)
_DOCUMENT_URL = "https://docs.google.com/document/d/{doc_id}/edit"


class FakeDocsAdapter:
    def __init__(self) -> None:
        self._docs: dict[str, list[str]] = {}

    def create_doc(self, title: str, body: str) -> str:
        doc_id = str(uuid.uuid4())
        self._docs[doc_id] = [body]
        return doc_id

    def append_text(self, doc_id: str, text: str) -> None:
        self._docs.setdefault(doc_id, []).append(text)


class DocsAdapter:
    """Real Google Docs v1 adapter using Application Default Credentials.

    Methods mirror FakeDocsAdapter (``create_doc`` / ``append_text``) so they
    satisfy the same Protocol contract. The additional ``populate_ma_memo``
    method writes M&A deal memo sections into the Doc referenced by the
    ``DOCS_MA_TEMPLATE_ID`` environment variable via ``documents.batchUpdate``
    and returns ``{"doc_id", "url"}``.
    """

    def __init__(self) -> None:
        if google_auth_default is None or build is None:  # pragma: no cover
            raise RuntimeError(
                "google-auth and google-api-python-client must be installed "
                "to use DocsAdapter; install the GCP optional deps."
            )
        creds, _ = google_auth_default(scopes=list(_DOCS_SCOPES))
        self._service = build("docs", "v1", credentials=creds, cache_discovery=False)
        self.template_id: str | None = os.environ.get("DOCS_MA_TEMPLATE_ID")

    # ------------------------------------------------------------------
    # Protocol-shared methods (mirror FakeDocsAdapter signatures)
    # ------------------------------------------------------------------

    def create_doc(self, title: str, body: str) -> str:
        """Create a new Doc with the given title and initial body text.

        Returns the ``documentId`` of the newly created document.
        """
        doc = self._service.documents().create(body={"title": title}).execute()
        doc_id: str = doc["documentId"]
        if body:
            self.append_text(doc_id, body)
        return doc_id

    def append_text(self, doc_id: str, text: str) -> None:
        """Append ``text`` to the end of the document identified by ``doc_id``."""
        self._service.documents().batchUpdate(
            documentId=doc_id,
            body={
                "requests": [
                    {"insertText": {"location": {"index": 1}, "text": text}}
                ]
            },
        ).execute()

    # ------------------------------------------------------------------
    # M&A deal memo rendering
    # ------------------------------------------------------------------

    def populate_ma_memo(
        self, doc_id: str, sections: dict[str, str]
    ) -> dict[str, str]:
        """Write M&A deal memo sections into ``doc_id`` via batchUpdate.

        Requires ``DOCS_MA_TEMPLATE_ID`` to be set so the caller can pair a
        freshly-copied template with the rendered content.

        Parameters
        ----------
        doc_id:
            The target document's ID (typically a copy of the template).
        sections:
            Ordered mapping of heading → body text, e.g.
            ``{"Executive Summary": "...", "Strategic Fit": "..."}``.

        Returns
        -------
        dict with keys ``"doc_id"`` and ``"url"``.
        """
        if not self.template_id:
            raise RuntimeError(
                "DOCS_MA_TEMPLATE_ID env var must be set to populate the "
                "M&A deal memo."
            )

        requests: list[dict] = []
        # Reversed so that when prepended at index 1 the sections appear in
        # the original dict order (last section inserted first ends up last).
        for heading, content in reversed(sections.items()):
            requests.extend(
                [
                    {
                        "insertText": {
                            "location": {"index": 1},
                            "text": f"\n{content}\n",
                        }
                    },
                    {
                        "insertText": {
                            "location": {"index": 1},
                            "text": f"{heading}\n",
                        }
                    },
                ]
            )

        if requests:
            self._service.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests}
            ).execute()

        return {
            "doc_id": doc_id,
            "url": _DOCUMENT_URL.format(doc_id=doc_id),
        }

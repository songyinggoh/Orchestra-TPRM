from __future__ import annotations

import uuid


class FakeDocsAdapter:
    def __init__(self) -> None:
        self._docs: dict[str, list[str]] = {}

    def create_doc(self, title: str, body: str) -> str:
        doc_id = str(uuid.uuid4())
        self._docs[doc_id] = [body]
        return doc_id

    def append_text(self, doc_id: str, text: str) -> None:
        self._docs.setdefault(doc_id, []).append(text)

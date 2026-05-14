"""P-1b: GoogleProvider.upload_file uploads via httpx, and
_messages_to_gemini_format emits fileData/inlineData parts when the source
Message carries attachments."""
from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx

from orchestra.core.types import Message, MessageRole
from orchestra.providers.google import GoogleProvider, _messages_to_gemini_format


def test_file_uri_attachment_emits_fileData_part():
    msg = Message(
        role=MessageRole.USER,
        content="Review this contract.",
        attachments=[
            {"file_uri": "https://generativelanguage.googleapis.com/v1beta/files/abc",
             "mime_type": "application/pdf"},
        ],
    )
    _, contents = _messages_to_gemini_format([msg])
    parts = contents[0]["parts"]
    assert any(
        p.get("fileData", {}).get("fileUri", "").endswith("/files/abc")
        and p["fileData"]["mimeType"] == "application/pdf"
        for p in parts
    )
    assert any("text" in p and p["text"] == "Review this contract." for p in parts)


def test_inline_data_b64_attachment_emits_inlineData_part():
    payload = base64.b64encode(b"hello").decode()
    msg = Message(
        role=MessageRole.USER,
        content="See inline.",
        attachments=[{"inline_data_b64": payload, "mime_type": "text/plain"}],
    )
    _, contents = _messages_to_gemini_format([msg])
    parts = contents[0]["parts"]
    assert any(
        p.get("inlineData", {}).get("data") == payload
        and p["inlineData"]["mimeType"] == "text/plain"
        for p in parts
    )


@pytest.mark.asyncio
@respx.mock
async def test_upload_file_returns_uri_and_mime():
    """Two-call upload protocol: start (POST) → upload (POST). The minimal
    contract we need: pass bytes + mime_type, get back {file_uri, mime_type}."""
    # Register the more-specific (params) route first so respx routes by
    # specificity: upload_route (with upload_id param) matches the finalize
    # call, start_route (no params) matches the initiation call.
    upload_route = respx.post(
        "https://generativelanguage.googleapis.com/upload/v1beta/files",
        params={"upload_id": "fake"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={"file": {"uri": "https://generativelanguage.googleapis.com/v1beta/files/xyz",
                            "mimeType": "application/pdf",
                            "name": "files/xyz",
                            "state": "ACTIVE"}},
        )
    )
    start_route = respx.post(
        "https://generativelanguage.googleapis.com/upload/v1beta/files"
    ).mock(
        return_value=httpx.Response(
            200,
            headers={
                "x-goog-upload-url": "https://generativelanguage.googleapis.com/upload/v1beta/files?upload_id=fake"
            },
        )
    )
    provider = GoogleProvider(api_key="test-key")
    result = await provider.upload_file(b"%PDF-1.4...", mime_type="application/pdf",
                                        display_name="msa.pdf")
    assert result["file_uri"].endswith("/files/xyz")
    assert result["mime_type"] == "application/pdf"
    assert start_route.called and upload_route.called
    await provider.aclose()

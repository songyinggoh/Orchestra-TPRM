"""P-1a: Message must accept an optional attachments list of dicts so callers
can attach Gemini Files API references or inline base64 blobs."""
from orchestra.core.types import Message, MessageRole


def test_message_accepts_attachments():
    msg = Message(
        role=MessageRole.USER,
        content="See attached SOC2.",
        attachments=[
            {"file_uri": "files/abc123", "mime_type": "application/pdf"},
        ],
    )
    assert msg.attachments == [
        {"file_uri": "files/abc123", "mime_type": "application/pdf"}
    ]


def test_message_attachments_default_none():
    msg = Message(role=MessageRole.USER, content="hi")
    assert msg.attachments is None

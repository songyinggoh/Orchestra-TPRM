"""W-3 prerequisite: SAFETY finish reason must be detectable. Today it is
silently mapped to "stop", indistinguishable from a clean completion."""
from orchestra.providers.google import _map_finish_reason


def test_safety_is_distinguishable_from_stop():
    assert _map_finish_reason("STOP") == "stop"
    assert _map_finish_reason("SAFETY") == "safety"


def test_other_reasons_unchanged():
    assert _map_finish_reason("MAX_TOKENS") == "length"
    assert _map_finish_reason("FUNCTION_CALL") == "tool_calls"

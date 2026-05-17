"""Tests for the Gemini CLI trust-workspace fix.

Covers:
- _gemini_env() always injects GEMINI_CLI_TRUST_WORKSPACE=true
- _gemini_env() respects the GEMINI_CLI_NO_TRUST_OVERRIDE escape hatch
- managed_proc forwards env= to asyncio.create_subprocess_exec
- complete() passes env= from _gemini_env() to managed_proc
- exit code 55 raises ProviderError with the exit code in the message
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestra.core.errors import ProviderError
from orchestra.core.types import Message, MessageRole
from orchestra.providers._cli_common import managed_proc
from orchestra.providers.gemini_cli import GeminiCliProvider, _gemini_env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user(content: str) -> Message:
    return Message(role=MessageRole.USER, content=content)


def _make_proc(returncode: int = 0, stdout: bytes = b'{"text":"ok"}', stderr: bytes = b"") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


# ---------------------------------------------------------------------------
# _gemini_env() unit tests
# ---------------------------------------------------------------------------

class TestGeminiEnv:
    def test_sets_trust_workspace(self):
        env = _gemini_env()
        assert env.get("GEMINI_CLI_TRUST_WORKSPACE") == "true"

    def test_inherits_parent_environment(self):
        with patch.dict(os.environ, {"MY_CUSTOM_VAR": "hello"}, clear=False):
            env = _gemini_env()
        assert env.get("MY_CUSTOM_VAR") == "hello"

    def test_is_a_copy_not_os_environ(self):
        env = _gemini_env()
        env["SHOULD_NOT_LEAK"] = "mutated"
        assert "SHOULD_NOT_LEAK" not in os.environ

    def test_escape_hatch_skips_override(self):
        with patch.dict(os.environ, {"GEMINI_CLI_NO_TRUST_OVERRIDE": "1"}, clear=False):
            env = _gemini_env()
        # Variable must NOT have been forcibly set to "true" —
        # it may be absent or carry whatever the parent env had.
        assert env.get("GEMINI_CLI_TRUST_WORKSPACE") != "true" or \
               os.environ.get("GEMINI_CLI_TRUST_WORKSPACE") == "true"

    def test_escape_hatch_empty_string_still_applies_override(self):
        # Only a truthy value in GEMINI_CLI_NO_TRUST_OVERRIDE disables the override.
        with patch.dict(os.environ, {"GEMINI_CLI_NO_TRUST_OVERRIDE": ""}, clear=False):
            env = _gemini_env()
        assert env.get("GEMINI_CLI_TRUST_WORKSPACE") == "true"


# ---------------------------------------------------------------------------
# managed_proc env= forwarding test
# ---------------------------------------------------------------------------

class TestManagedProcEnvForwarding:
    @pytest.mark.asyncio
    async def test_forwards_env_to_subprocess(self):
        custom_env = {"SOME_VAR": "value", "PATH": os.environ.get("PATH", "")}
        captured: dict = {}

        async def fake_exec(*cmd, stdin, stdout, stderr, env):
            captured["env"] = env
            proc = MagicMock()
            proc.returncode = 0
            proc.kill = MagicMock()
            proc.wait = AsyncMock(return_value=0)
            return proc

        with patch("orchestra.providers._cli_common.asyncio.create_subprocess_exec", side_effect=fake_exec):
            async with managed_proc("echo", "hi", env=custom_env):
                pass

        assert captured["env"] is custom_env

    @pytest.mark.asyncio
    async def test_none_env_passes_none_to_subprocess(self):
        """When env= is omitted, None is forwarded so the child inherits parent env."""
        captured: dict = {}

        async def fake_exec(*cmd, stdin, stdout, stderr, env):
            captured["env"] = env
            proc = MagicMock()
            proc.returncode = 0
            proc.kill = MagicMock()
            proc.wait = AsyncMock(return_value=0)
            return proc

        with patch("orchestra.providers._cli_common.asyncio.create_subprocess_exec", side_effect=fake_exec):
            async with managed_proc("echo", "hi"):
                pass

        assert captured["env"] is None


# ---------------------------------------------------------------------------
# GeminiCliProvider.complete() uses _gemini_env()
# ---------------------------------------------------------------------------

class TestCompleteUsesGeminiEnv:
    @pytest.mark.asyncio
    async def test_complete_passes_gemini_env_to_managed_proc(self):
        sentinel_env = {"GEMINI_CLI_TRUST_WORKSPACE": "true", "SENTINEL": "yes"}
        captured: dict = {}

        async def fake_exec(*cmd, stdin, stdout, stderr, env):
            captured["env"] = env
            proc = _make_proc(returncode=0, stdout=b"hello world")
            return proc

        with patch("orchestra.providers.gemini_cli._gemini_env", return_value=sentinel_env), \
             patch("orchestra.providers._cli_common.asyncio.create_subprocess_exec", side_effect=fake_exec):
            provider = GeminiCliProvider(gemini_path="gemini")
            await provider.complete([_user("hi")])

        assert captured.get("env") is sentinel_env


# ---------------------------------------------------------------------------
# Exit code 55 raises ProviderError
# ---------------------------------------------------------------------------

class TestExitCode55:
    @pytest.mark.asyncio
    async def test_exit_code_55_raises_provider_error(self):
        stderr_msg = (
            "YOLO mode is enabled.\n"
            "Gemini CLI is not running in a trusted directory.\n"
            "To proceed, use --skip-trust or set GEMINI_CLI_TRUST_WORKSPACE=true."
        )

        async def fake_exec(*cmd, stdin, stdout, stderr, env):
            return _make_proc(returncode=55, stdout=b"", stderr=stderr_msg.encode())

        with patch("orchestra.providers._cli_common.asyncio.create_subprocess_exec", side_effect=fake_exec):
            provider = GeminiCliProvider(gemini_path="gemini")
            with pytest.raises(ProviderError, match="55"):
                await provider.complete([_user("test")])

    @pytest.mark.asyncio
    async def test_exit_code_55_error_includes_stderr(self):
        trust_hint = "not running in a trusted directory"

        async def fake_exec(*cmd, stdin, stdout, stderr, env):
            return _make_proc(returncode=55, stdout=b"", stderr=trust_hint.encode())

        with patch("orchestra.providers._cli_common.asyncio.create_subprocess_exec", side_effect=fake_exec):
            provider = GeminiCliProvider(gemini_path="gemini")
            with pytest.raises(ProviderError, match=trust_hint):
                await provider.complete([_user("test")])

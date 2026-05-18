"""Gemini CLI provider — uses your Google subscription directly.

No API key required. Invokes the ``gemini`` CLI as a subprocess, so
Orchestra piggybacks on your existing Google / Gemini Advanced subscription.

The Gemini CLI (https://github.com/google-gemini/gemini-cli) authenticates
via your Google account. If you can run ``gemini`` in your terminal, this
provider works automatically.

Usage:
    from orchestra.providers.gemini_cli import GeminiCliProvider

    provider = GeminiCliProvider()                          # default model
    provider = GeminiCliProvider(model="gemini-2.5-pro")    # pick a model
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from collections.abc import AsyncIterator
from typing import Any

from orchestra.core.errors import ProviderError, ProviderUnavailableError
from orchestra.core.types import (
    LLMResponse,
    Message,
    ModelCost,
    StreamChunk,
    TokenUsage,
    ToolCall,
)
from orchestra.providers._cli_common import (
    inject_tools_into_system,
    managed_proc,
    messages_to_prompt,
    parse_tool_calls,
    strip_tool_calls,
)

_logger = logging.getLogger(__name__)

# Module-level gate that limits concurrent Gemini CLI invocations.
# Defaults to 5 (enough for the 5-specialist fan-out in TPRM).
# Set GEMINI_CLI_CONCURRENCY=1 to restore the original serial behaviour.
_GEMINI_CLI_GATE = asyncio.Semaphore(int(os.getenv("GEMINI_CLI_CONCURRENCY", "5")))

# Detects the "quota exhausted" message the CLI surfaces in stderr.
# Capture group 1 is the reset-after hint (seconds) when present.
_QUOTA_RX = re.compile(
    r"exhausted your capacity|quota will reset after (\d+)|rate.?limit|\b429\b",
    re.IGNORECASE,
)
_DEFAULT_QUOTA_BACKOFF_SECONDS = 45

# Detects safety-blocked CLI responses (empty stdout + safety banner on stderr).
_SAFETY_RX = re.compile(
    r"blocked|safety|harmful|violat|content.?policy",
    re.IGNORECASE,
)

# Exit code 55 = "not trusted directory" — the CLI refuses to run in
# non-interactive mode when --skip-trust is absent and the workspace has
# not been trusted interactively.  We pass --skip-trust in every invocation
# so this code should never appear, but we keep the constant for the
# error-message hint below.
_EXIT_CODE_NOT_TRUSTED = 55


def _gemini_env() -> dict[str, str]:
    """Return an environment dict for Gemini CLI subprocesses.

    Inherits the full parent environment and unconditionally sets
    ``GEMINI_CLI_TRUST_WORKSPACE=true`` so the CLI never exits with the
    "not trusted directory" error (exit code 55) when running non-interactively.

    On Cloud Run the variable is typically already set; overwriting it with
    the same value is harmless.  To opt out locally, set
    ``GEMINI_CLI_NO_TRUST_OVERRIDE=1`` in the parent environment.
    """
    env = dict(os.environ)
    if not os.environ.get("GEMINI_CLI_NO_TRUST_OVERRIDE"):
        env["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
    return env


class GeminiCliProvider:
    """LLM provider that delegates to the ``gemini`` CLI.

    Requires only a Google account — no ``GOOGLE_API_KEY`` or any other
    billing account.  Each ``complete()`` call spawns the ``gemini`` CLI
    as a subprocess.

    Tool calling is supported via prompt engineering: tools are described
    in the system prompt and the model replies with a ``<tool_calls>``
    block that Orchestra parses automatically.
    """

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        timeout: float = 240.0,
        gemini_path: str | None = None,
    ) -> None:
        self._default_model = model
        self._timeout = timeout
        self._gemini_path = gemini_path or shutil.which("gemini") or "gemini"

    @property
    def provider_name(self) -> str:
        return "gemini_cli"

    @property
    def default_model(self) -> str:
        return self._default_model

    async def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        output_type: Any = None,
    ) -> LLMResponse:
        """Send a completion request via the ``gemini`` CLI."""
        use_model = model or self._default_model
        system, prompt = messages_to_prompt(messages)

        if tools:
            system = inject_tools_into_system(system, tools)

        # Build prompt payload; --prompt " " activates headless/non-interactive
        # mode (required by Gemini CLI >= 0.42); actual content is piped via stdin
        # (the CLI appends --prompt value after stdin, so a single space is harmless).
        stdin_payload = prompt
        if system:
            stdin_payload = f"[system]\n{system}\n\n[user]\n{prompt}"

        cmd: list[str] = [
            self._gemini_path,
            "--model",
            use_model,
            "--prompt",
            " ",  # activates headless mode; real content arrives via stdin
            "--yolo",  # suppress interactive confirmation prompts (e.g. MCP auth)
            "--skip-trust",  # bypass "not trusted directory" guard (exit code 55)
        ]

        # Subprocess environment: inherit parent env and add trust override so
        # the Gemini CLI does not exit with code 55 ("not trusted directory").
        proc_env = _gemini_env()

        # Quota-aware retry loop. Each attempt acquires the global gate
        # only for the subprocess call itself; the backoff sleep happens
        # OUTSIDE the gate so other callers can interleave during the wait.
        last_err: ProviderError | None = None
        stdout: bytes = b""
        for attempt in range(2):  # 1 initial try + 1 retry on rate-limit
            try:
                async with _GEMINI_CLI_GATE:
                    _logger.debug("gemini_cli_gate_acquired attempt=%s", attempt)
                    async with managed_proc(*cmd, env=proc_env) as proc:
                        try:
                            stdout, stderr = await asyncio.wait_for(
                                proc.communicate(stdin_payload.encode()),
                                timeout=self._timeout,
                            )
                        except TimeoutError:
                            raise ProviderError(
                                f"gemini CLI timed out after {self._timeout}s. "
                                "Increase timeout= or simplify the prompt."
                            ) from None
                    if proc.returncode != 0:
                        err_text = stderr.decode(errors="replace").strip()
                        if proc.returncode == _EXIT_CODE_NOT_TRUSTED:
                            raise ProviderError(
                                f"gemini CLI exited with code {proc.returncode} "
                                "(not trusted directory). "
                                "The --skip-trust flag was passed but was not "
                                "recognised by this CLI version. "
                                "Fix: upgrade the Gemini CLI, or run "
                                "`gemini` once interactively in this directory "
                                "to add it to the trusted-workspace list.\n"
                                f"  stderr: {err_text[:500]}"
                            )
                        raise ProviderError(
                            f"gemini CLI exited with code {proc.returncode}.\n"
                            f"  stderr: {err_text[:500]}"
                        )
            except FileNotFoundError:
                raise ProviderUnavailableError(
                    "The 'gemini' CLI was not found on PATH.\n"
                    "  Fix: Install the Gemini CLI (https://github.com/google-gemini/gemini-cli) "
                    "or pass gemini_path= to GeminiCliProvider."
                ) from None
            except ProviderError as e:
                last_err = e
                hint = _QUOTA_RX.search(str(e))
                if hint is None or attempt == 1:
                    raise
                secs = hint.group(1)
                sleep_s = int(secs) + 3 if secs else _DEFAULT_QUOTA_BACKOFF_SECONDS
                _logger.warning(
                    "gemini_quota_backoff sleep=%ss attempt=%s hint=%s",
                    sleep_s, attempt, secs or "default",
                )
                await asyncio.sleep(sleep_s)
                continue
            # Success — break out of retry loop.
            break
        else:
            # Loop exhausted without success
            if last_err is not None:
                raise last_err

        raw_output = stdout.decode(errors="replace").strip()
        stderr_text = stderr.decode(errors="replace") if stderr else ""

        # Detect safety-blocked response: empty stdout + safety banner in stderr.
        if not raw_output and _SAFETY_RX.search(stderr_text):
            _logger.warning("gemini_cli_safety_block model=%s", use_model)
            return LLMResponse(
                content="",
                finish_reason="safety",
                usage=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0, estimated_cost_usd=0.0),
                model=use_model,
            )

        # Try JSON first (gemini may output structured JSON).
        data: dict[str, Any] | None = None
        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError:
            pass

        if data and isinstance(data, dict):
            return self._parse_json_response(data, use_model, tools)

        # Fall back to plain text response.
        return self._parse_text_response(raw_output, use_model, tools)

    async def stream(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion via the ``gemini`` CLI."""
        use_model = model or self._default_model
        system, prompt = messages_to_prompt(messages)

        if tools:
            system = inject_tools_into_system(system, tools)

        stdin_payload = prompt
        if system:
            stdin_payload = f"[system]\n{system}\n\n[user]\n{prompt}"

        cmd: list[str] = [
            self._gemini_path,
            "--model",
            use_model,
            "--prompt",
            " ",  # activates headless mode
            "--yolo",  # suppress interactive confirmation prompts
            "--skip-trust",  # bypass "not trusted directory" guard (exit code 55)
        ]

        # Subprocess environment: same trust override as complete().
        proc_env = _gemini_env()

        try:
            async with managed_proc(*cmd, env=proc_env) as proc:
                assert proc.stdin is not None
                assert proc.stdout is not None

                proc.stdin.write(stdin_payload.encode())
                proc.stdin.close()

                async for raw_line in proc.stdout:
                    line = raw_line.decode(errors="replace").strip()
                    if not line:
                        continue

                    # Try to parse as JSON event (streaming JSON mode).
                    try:
                        event = json.loads(line)
                        text = event.get("text", event.get("content", ""))
                        if text:
                            yield StreamChunk(content=text, model=use_model)
                        if event.get("done") or event.get("type") == "result":
                            yield StreamChunk(content="", finish_reason="stop", model=use_model)
                        continue
                    except json.JSONDecodeError:
                        pass

                    # Plain text line — yield as content.
                    yield StreamChunk(content=line, model=use_model)

                yield StreamChunk(content="", finish_reason="stop", model=use_model)
                await proc.wait()
        except FileNotFoundError:
            raise ProviderUnavailableError(
                "The 'gemini' CLI was not found on PATH.\n  Fix: Install the Gemini CLI."
            ) from None

    def count_tokens(self, messages: list[Message], model: str | None = None) -> int:
        """Approximate token count (4 chars per token heuristic)."""
        total = 0
        for msg in messages:
            total += len(msg.content or "") // 4 + 4
        return total

    def get_model_cost(self, model: str | None = None) -> ModelCost:
        """Cost is zero — covered by the Google / Gemini subscription."""
        return ModelCost(input_cost_per_1k=0.0, output_cost_per_1k=0.0)

    def _parse_json_response(
        self,
        data: dict[str, Any],
        model: str,
        tools: list[dict[str, Any]] | None,
    ) -> LLMResponse:
        """Parse structured JSON output from the CLI."""
        result_text: str = data.get("result", data.get("text", data.get("content", ""))) or ""

        tool_calls: list[ToolCall] = []
        content = result_text
        if tools:
            parsed = parse_tool_calls(result_text)
            if parsed:
                tool_calls = parsed
                content = strip_tool_calls(result_text) or ""

        finish_reason = "tool_calls" if tool_calls else "stop"

        raw_usage = data.get("usage", data.get("usageMetadata", {}))
        input_tok = raw_usage.get("input_tokens", raw_usage.get("promptTokenCount", 0))
        output_tok = raw_usage.get("output_tokens", raw_usage.get("candidatesTokenCount", 0))

        usage = TokenUsage(
            input_tokens=input_tok,
            output_tokens=output_tok,
            total_tokens=input_tok + output_tok,
            estimated_cost_usd=0.0,
        )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            model=model,
            raw_response=data,
        )

    def _parse_text_response(
        self,
        text: str,
        model: str,
        tools: list[dict[str, Any]] | None,
    ) -> LLMResponse:
        """Parse plain text output from the CLI."""
        tool_calls: list[ToolCall] = []
        content: str | None = text
        if tools:
            parsed = parse_tool_calls(text)
            if parsed:
                tool_calls = parsed
                content = strip_tool_calls(text)

        finish_reason = "tool_calls" if tool_calls else "stop"

        # Approximate usage from text length.
        input_tok = len(text) // 4
        output_tok = len(text) // 4

        usage = TokenUsage(
            input_tokens=input_tok,
            output_tokens=output_tok,
            total_tokens=input_tok + output_tok,
            estimated_cost_usd=0.0,
        )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            model=model,
        )

    async def aclose(self) -> None:
        """No persistent connections to close."""

    @staticmethod
    def is_available() -> bool:
        """Return True if the ``gemini`` CLI is on PATH."""
        return shutil.which("gemini") is not None

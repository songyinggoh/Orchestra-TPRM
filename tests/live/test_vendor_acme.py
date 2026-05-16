"""Live vendor-mode smoke test against the Acme demo packet.

Invokes the orchestra-tprm CLI as a subprocess against the synthetic
Acme packet and asserts the full pipeline produces findings from every
specialist. This is the canary that gates demo-readiness — it must be
GREEN before recording the submission video.

NOT in CI: live Gemini CLI calls hit the user's per-minute subscription
quota. Run manually:

    pytest tests/live/test_vendor_acme.py -m live -v

Skipped automatically if:
  - ``gemini`` CLI is not on PATH
  - GOOGLE_CLOUD_PROJECT env var is unset
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.live


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACME_PACKET = _REPO_ROOT / "examples" / "tprm" / "acme"
_EXPECTED_SPECIALISTS = {"LegalAgent", "SecurityAgent", "ExternalAgent", "CodeAgent"}


def _load_env_for_subprocess() -> dict[str, str]:
    """Best-effort .env loader so the subprocess inherits GCP config.

    Mirrors src/orchestra_tprm/cli.py::_load_env so the test runs without
    requiring manual shell exports. .env values DO NOT override real env.
    """
    env = dict(os.environ)
    p = _REPO_ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip())
    return env


def _skip_if_unavailable(env: dict[str, str]) -> None:
    if shutil.which("gemini") is None:
        pytest.skip("gemini CLI not on PATH — live demo cannot run")
    if not env.get("GOOGLE_CLOUD_PROJECT"):
        pytest.skip("GOOGLE_CLOUD_PROJECT unset (check .env) — live GCP adapters cannot run")
    if not _ACME_PACKET.exists():
        pytest.skip(f"Acme packet not found at {_ACME_PACKET}")


def test_vendor_acme_live_smoke(tmp_path: Path) -> None:
    """End-to-end live run on the Acme packet must produce ≥4 non-error
    findings, one per active specialist, plus a policy verdict.

    Currently RED until the local:// URI inline-text fix lands — Legal
    will surface as an agent-error and Security/External will be silent.
    """
    env = _load_env_for_subprocess()
    _skip_if_unavailable(env)

    out_path = tmp_path / "verdict.json"
    try:
        proc = subprocess.run(
            ["orchestra-tprm",
             "--mode", "vendor",
             "--packet", str(_ACME_PACKET),
             "--out", str(out_path),
             "--no-dashboard"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=420,
            env=env,
        )
    except FileNotFoundError:
        pytest.fail("orchestra-tprm entry point not found — is the package installed?")
    except subprocess.TimeoutExpired:
        pytest.fail("Live demo exceeded 7-minute timeout — provider hung or rate-limited")

    assert out_path.exists(), (
        f"verdict.json was not written. stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )

    verdict = json.loads(out_path.read_text(encoding="utf-8"))
    findings = verdict.get("findings", [])

    # --- Coverage: every specialist must contribute at least one finding ---
    agents_emitting = {f.get("agent") for f in findings}
    missing = _EXPECTED_SPECIALISTS - agents_emitting
    assert not missing, (
        f"Specialists silent in live run: {missing}. "
        f"Agents seen: {agents_emitting}. Findings: {findings!r}"
    )

    # --- Quality: each specialist must emit at least one NON-error finding ---
    by_agent: dict[str, list[dict]] = {}
    for f in findings:
        by_agent.setdefault(f.get("agent", ""), []).append(f)
    error_only = {
        agent
        for agent, items in by_agent.items()
        if agent in _EXPECTED_SPECIALISTS
        and all(item.get("category") in {"agent-error", "parse-error", "extract-error"}
                for item in items)
    }
    assert not error_only, (
        f"Specialists emitted only error findings: {error_only}. "
        f"Per-agent findings: { {a: [i.get('category') for i in xs] for a, xs in by_agent.items()} }"
    )

    # --- Total count ---
    assert len(findings) >= 4, (
        f"Expected ≥4 findings (one per specialist), got {len(findings)}: "
        f"{[(f.get('agent'), f.get('category')) for f in findings]}"
    )

    # --- Policy verdict surfaced ---
    assert verdict.get("policy_verdict"), (
        f"policy_verdict missing from verdict.json: {verdict!r}"
    )

    # --- Evidence trail: at least one finding cites the MSA ---
    cited_files = {
        cite.get("file_id")
        for f in findings
        for cite in (f.get("evidence") or [])
        if isinstance(cite, dict)
    }
    assert any("msa" in str(fid).lower() for fid in cited_files), (
        f"No finding cites the MSA document; cited files: {cited_files}"
    )

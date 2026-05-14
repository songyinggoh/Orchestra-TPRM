"""ModeConfig — the only place where per-mode behavior is declared.

Specialists, Coordinator, and PolicyAgent read this object at runtime. They
must contain ZERO `if mode == "vendor"` or `if mode == "ma"` literals.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

_MODES_DIR = Path(__file__).parent


class SpecialistModels(BaseModel):
    legal: str | None = None
    financial: str | None = None
    security: str | None = None
    code: str | None = None
    external: str | None = None


class ModeConfig(BaseModel):
    name: Literal["vendor", "ma"]
    intake_model: str
    router_model: str
    specialists: SpecialistModels
    policy_model: str
    coordinator_model: str
    coordinator_template: str
    policy_pack: str
    output_kind: Literal["sheet", "doc"]
    code_agent_generates_patch: bool = False


def load_mode(name: str) -> ModeConfig:
    yaml_path = _MODES_DIR / f"{name}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"No mode config at {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    raw["coordinator_template"] = str((_MODES_DIR / raw["coordinator_template"]).resolve())
    raw["policy_pack"] = str(
        (Path(__file__).parent.parent / "policies" / raw["policy_pack"]).resolve()
    )
    return ModeConfig(**raw)

"""The set of available reasoning backends and how to build each. Generic; no compound knowledge.
Secrets live in the environment (never here); non-secret endpoint config (labels, base URLs, model
names) persists to a gitignored local file so user-added and edited endpoints survive restarts.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from .adapter import ClaudeReasoningModel, ReasoningModel
from .openai_compatible import OpenAICompatibleReasoningModel

# repo-root/data/models.local.json — gitignored; non-secret config only (never a key).
_CONFIG = Path(__file__).resolve().parents[2] / "data" / "models.local.json"


@dataclass
class ModelEntry:
    id: str
    label: str
    kind: str  # "claude" | "openai_compatible"
    model: str
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    builtin: bool = False


_BUILTIN = [
    ModelEntry("claude", "Claude", "claude", "claude-opus-4-8", api_key_env="ANTHROPIC_API_KEY", builtin=True),
    ModelEntry(
        "openai", "ChatGPT", "openai_compatible", "gpt-4o",
        base_url="https://api.openai.com/v1", api_key_env="OPENAI_API_KEY", builtin=True,
    ),
    ModelEntry(
        "local", "Local", "openai_compatible", "qwen2.5:14b-instruct",
        base_url="http://localhost:11434/v1", api_key_env=None, builtin=True,
    ),
]
_BUILTIN_IDS = {e.id for e in _BUILTIN}


def _load_overrides() -> dict:
    if _CONFIG.exists():
        try:
            return json.loads(_CONFIG.read_text())
        except Exception:
            return {}
    return {}


def load_registry() -> list:
    """Built-in entries (with any base_url/model overrides applied) plus user-added endpoints."""
    overrides = _load_overrides()
    entries = []
    for e in _BUILTIN:
        ov = overrides.get(e.id, {})
        entries.append(replace(e, base_url=ov.get("base_url", e.base_url), model=ov.get("model", e.model)))
    for eid, cfg in overrides.items():
        if eid in _BUILTIN_IDS:
            continue
        entries.append(
            ModelEntry(
                id=eid, label=cfg["label"], kind="openai_compatible", model=cfg["model"],
                base_url=cfg["base_url"], api_key_env=cfg.get("api_key_env"),
            )
        )
    return entries


def status(entry: ModelEntry) -> str:
    """``ready`` (usable now), ``no_key`` (its env key is unset), or ``unconfigured`` (no endpoint)."""
    if entry.kind == "claude":
        return "ready" if os.environ.get(entry.api_key_env or "") else "no_key"
    if not entry.base_url:
        return "unconfigured"
    if entry.api_key_env and not os.environ.get(entry.api_key_env):
        return "no_key"
    return "ready"


def build_model(entry: ModelEntry) -> ReasoningModel:
    if entry.kind == "claude":
        return ClaudeReasoningModel(model=entry.model, effort="medium")
    return OpenAICompatibleReasoningModel(model=entry.model, base_url=entry.base_url, api_key_env=entry.api_key_env)


def save_endpoint(id: str, label: str, base_url: str, model: str, api_key_env: Optional[str] = None) -> None:
    """Persist a built-in override or a new endpoint to the gitignored config (never a key)."""
    overrides = _load_overrides()
    overrides[id] = {"label": label, "base_url": base_url, "model": model, "api_key_env": api_key_env}
    _CONFIG.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG.write_text(json.dumps(overrides, indent=2))

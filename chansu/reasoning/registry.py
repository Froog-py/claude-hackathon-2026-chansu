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
    """Read the gitignored config. On an unreadable/unparseable file, or one that is not a JSON object,
    degrade to no overrides so the built-in models stay available (a bad local file never bricks the
    app). Malformed *individual* entries are skipped in ``load_registry``, not here."""
    if not _CONFIG.exists():
        return {}
    try:
        data = json.loads(_CONFIG.read_text())
    except (OSError, ValueError):  # unreadable file or invalid JSON — not every exception
        return {}
    return data if isinstance(data, dict) else {}


def load_registry() -> list:
    """Built-in entries (with any persisted overrides applied) plus user-added endpoints. A built-in's
    label, base_url, model, and api_key_env can each be overridden; its id and kind never change. A
    malformed user entry (not an object, or missing a required field) is skipped rather than crashing
    the whole registry with a KeyError."""
    overrides = _load_overrides()
    entries = []
    for e in _BUILTIN:
        ov = overrides.get(e.id)
        if not isinstance(ov, dict):
            ov = {}
        entries.append(replace(
            e,
            label=ov.get("label", e.label),
            base_url=ov.get("base_url", e.base_url),
            model=ov.get("model", e.model),
            api_key_env=ov.get("api_key_env", e.api_key_env),
        ))
    for eid, cfg in overrides.items():
        if eid in _BUILTIN_IDS:
            continue
        if not isinstance(cfg, dict) or not (cfg.get("label") and cfg.get("base_url") and cfg.get("model")):
            continue  # skip a malformed user entry instead of raising mid-registry
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
    """Persist a built-in override or a new endpoint to the gitignored config (never a key). A plain
    ``http://`` endpoint is refused when an ``api_key_env`` is set, so a key never travels in cleartext;
    keyless http (a local/LAN model) and any https endpoint are allowed."""
    if api_key_env and base_url.strip().lower().startswith("http://"):
        raise ValueError(
            "refusing to store an http:// endpoint that carries an API key (the key would travel in "
            "cleartext). Use https for a keyed endpoint; http is allowed only for a keyless local model."
        )
    overrides = _load_overrides()
    overrides[id] = {"label": label, "base_url": base_url, "model": model, "api_key_env": api_key_env}
    _CONFIG.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG.write_text(json.dumps(overrides, indent=2))

# Multi-Model Reasoning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Point-in-time note:** a build guide. Where it differs from the shipped result, the code in `chansu/` and `docs/multi-model-design.md` are authoritative.

**Goal:** Make the reasoning layer model-pluggable — run Claude, ChatGPT, or a local model (or all), compare side by side, export the comparison, and let a user connect their own model, with keys only ever in the environment.

**Architecture:** A second adapter (`OpenAICompatibleReasoningModel`) behind the existing `ReasoningModel` Protocol covers OpenAI + Ollama + any `/v1/chat/completions` endpoint. A registry lists backends (built-in + user-added; secrets from env, non-secret config in a gitignored file). The Design-memo page gains a model multi-select + "Run reasoning" + side-by-side render + expanded checks. A pure function builds a downloadable comparison README.

**Tech Stack:** Python 3.12, the `openai` SDK (new dep; targets OpenAI + Ollama unchanged via `base_url`), Streamlit. The deterministic memo is untouched.

## Global Constraints

- **Python 3.12 in `.venv`.** Test: `.venv/bin/python -m pytest -q`. Run app: `.venv/bin/streamlit run chansu/ui/app.py`.
- **New dependency:** `uv pip install --python .venv/bin/python openai` (Task 1). The `anthropic` SDK is already present for the Claude backend.
- **Generic engine (PROJECT.md §5):** no compound-specific tokens anywhere in `chansu/`. `tests/test_core.py::test_generic_engine_rule` stays green. The registry's built-in `local` endpoint defaults to `http://localhost:11434/v1` (no hardcoded demo IP in committed code); the real endpoint is set in-app and persisted to the gitignored config.
- **Trust boundary (PROJECT.md §6):** keys read from the environment at call time, never stored, logged, or committed. Every model's output is provenance-tagged; declines render in the calm `.cs-declined` register, never as errors. The deterministic memo is the floor regardless of any model.
- **Design system (chansu-design skill):** reuse the `.cs-*` contract; three type registers; §7 states; §8 voice (no em dashes, no AI lexis). Run `chansu-theme-review` on any UI before committing it.
- **Commits:** Luke's standing rule — never commit or push without his explicit OK. The `git commit` steps are the intended boundaries; surface each and get his go.

**Working directory:** the `feature/multi-model-reasoning` worktree.

---

### Task 1: `OpenAICompatibleReasoningModel` + mock tests

**Files:**
- Create: `chansu/reasoning/openai_compatible.py`
- Test: `tests/test_openai_compatible.py`

**Interfaces:**
- Consumes (from `chansu/reasoning/adapter.py`): `BaseReasoningModel`, `Message`, `ReasoningRequest`, `ReasoningResponse`, `ReasoningError`, `ReasoningTimeout`, `Usage`, `_is_timeout`.
- Produces: `OpenAICompatibleReasoningModel(model, base_url, api_key_env=None, default_max_tokens=2048, client=None)` implementing `ReasoningModel`; `name -> model`; `complete(request) -> ReasoningResponse`; internal `_api_key()`, `_to_response(resp)`.

- [ ] **Step 0: Install the dependency**

Run: `uv pip install --python .venv/bin/python openai`
Expected: `openai` installed.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_openai_compatible.py
import pytest

from chansu.reasoning.adapter import Message, ReasoningError, ReasoningRequest
from chansu.reasoning.openai_compatible import OpenAICompatibleReasoningModel


class _Msg:
    def __init__(self, content): self.content = content
class _Choice:
    def __init__(self, content, finish): self.message = _Msg(content); self.finish_reason = finish
class _Usage:
    def __init__(self, p, c): self.prompt_tokens = p; self.completion_tokens = c
class _Resp:
    def __init__(self, content="hi", finish="stop", usage=(10, 5)):
        self.choices = [_Choice(content, finish)]
        self.usage = _Usage(*usage) if usage else None
class _Completions:
    def __init__(self, resp, spy=None): self._resp = resp; self._spy = spy
    def create(self, **kwargs):
        if self._spy is not None: self._spy.update(kwargs)
        return self._resp
class _Chat:
    def __init__(self, resp, spy=None): self.completions = _Completions(resp, spy)
class _Client:
    def __init__(self, resp, spy=None): self.chat = _Chat(resp, spy)


def _model(resp, spy=None):
    return OpenAICompatibleReasoningModel(model="m", base_url="http://x/v1", client=_Client(resp, spy))


def _req():
    return ReasoningRequest(system="SYS", messages=[Message("user", "U")], max_tokens=32)


def test_maps_text_and_stop_and_usage():
    r = _model(_Resp("answer", "stop", (7, 3))).complete(_req())
    assert r.text == "answer"
    assert r.stop_reason == "end_turn"          # openai "stop" -> interface "end_turn"
    assert r.usage.input_tokens == 7 and r.usage.output_tokens == 3


def test_finish_reason_mapping():
    assert _model(_Resp(finish="length")).complete(_req()).stop_reason == "max_tokens"
    assert _model(_Resp(finish="content_filter")).complete(_req()).stop_reason == "refusal"


def test_system_prompt_becomes_first_message():
    spy = {}
    _model(_Resp(), spy).complete(_req())
    assert spy["messages"][0] == {"role": "system", "content": "SYS"}
    assert spy["model"] == "m" and spy["max_tokens"] == 32


def test_missing_key_raises_reasoning_error():
    m = OpenAICompatibleReasoningModel(model="m", base_url="http://x/v1", api_key_env="DEFINITELY_UNSET_XYZ")
    with pytest.raises(ReasoningError):
        m._api_key()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_openai_compatible.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the implementation**

```python
# chansu/reasoning/openai_compatible.py
"""OpenAI-compatible reasoning backend: one adapter for OpenAI, a local Ollama/vLLM server, and any
endpoint that speaks /v1/chat/completions. Same ReasoningModel interface as the Claude backend. The
key is read from the environment at call time and never stored (PROJECT.md §6)."""
from __future__ import annotations

import os
from typing import Any, Optional

from .adapter import (
    BaseReasoningModel, ReasoningError, ReasoningRequest, ReasoningResponse, ReasoningTimeout, Usage, _is_timeout,
)

# OpenAI finish_reason -> the interface's stop_reason vocabulary (what the memo + checks understand)
_FINISH_MAP = {"stop": "end_turn", "length": "max_tokens", "content_filter": "refusal", "tool_calls": "tool_use"}


class OpenAICompatibleReasoningModel(BaseReasoningModel):
    """Backend for any OpenAI-style chat-completions endpoint. ``api_key_env`` is the *name* of the env
    var holding the key (None for keyless local servers). Inject ``client`` to unit-test without the SDK."""

    def __init__(self, model: str, base_url: str, api_key_env: Optional[str] = None,
                 default_max_tokens: int = 2048, client: Any = None) -> None:
        self.model = model
        self.base_url = base_url
        self.api_key_env = api_key_env
        self.default_max_tokens = default_max_tokens
        self._client = client

    @property
    def name(self) -> str:
        return self.model

    def _api_key(self) -> str:
        if self.api_key_env:
            key = os.environ.get(self.api_key_env)
            if not key:
                raise ReasoningError(f"{self.api_key_env} is not set in the environment")
            return key
        return "local"  # keyless servers ignore it, but the SDK requires a non-empty value

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import openai
            except ImportError as exc:
                raise ReasoningError("the 'openai' package is required (pip install openai)") from exc
            self._client = openai.OpenAI(base_url=self.base_url, api_key=self._api_key())
        return self._client

    def complete(self, request: ReasoningRequest) -> ReasoningResponse:
        client = self._get_client()
        max_tokens = request.max_tokens if request.max_tokens is not None else self.default_max_tokens
        messages = [{"role": "system", "content": request.system}] if request.system else []
        messages += [{"role": m.role, "content": m.content} for m in request.messages]
        params: dict = {"model": self.model, "messages": messages, "max_tokens": max_tokens,
                        "temperature": request.temperature}
        if request.stop_sequences:
            params["stop"] = request.stop_sequences
        try:
            resp = client.chat.completions.create(**params)
        except Exception as exc:
            if _is_timeout(exc):
                raise ReasoningTimeout(f"request timed out: {exc}") from exc
            raise ReasoningError(f"request failed: {exc}") from exc
        try:
            return self._to_response(resp)
        except ReasoningError:
            raise
        except Exception as exc:
            raise ReasoningError(f"could not decode response: {exc}") from exc

    @staticmethod
    def _to_response(resp: Any) -> ReasoningResponse:
        choices = getattr(resp, "choices", None)
        if not choices:
            raise ReasoningError("malformed response: no choices")
        choice = choices[0]
        text = getattr(getattr(choice, "message", None), "content", None) or ""
        finish = getattr(choice, "finish_reason", None) or "stop"
        raw_usage = getattr(resp, "usage", None)
        usage = Usage(input_tokens=getattr(raw_usage, "prompt_tokens", None),
                      output_tokens=getattr(raw_usage, "completion_tokens", None)) if raw_usage else None
        return ReasoningResponse(text=text, stop_reason=_FINISH_MAP.get(finish, finish), usage=usage, raw=resp)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_openai_compatible.py -q`
Expected: PASS. (The shipped suite has since grown; the code is authoritative per the header note.)

- [ ] **Step 5: Commit** (get Luke's OK)

```bash
git add chansu/reasoning/openai_compatible.py tests/test_openai_compatible.py
git commit -m "feat(reasoning): OpenAI-compatible adapter (OpenAI + Ollama + any /v1)"
```

---

### Task 2: Model registry + gitignored config

**Files:**
- Create: `chansu/reasoning/registry.py`
- Modify: `.gitignore` (add `data/models.local.json`)
- Test: `tests/test_registry.py`

**Interfaces:**
- Consumes: `ClaudeReasoningModel` (adapter), `OpenAICompatibleReasoningModel` (Task 1).
- Produces: `ModelEntry(id, label, kind, model, base_url=None, api_key_env=None, builtin=False)`; `load_registry() -> list[ModelEntry]`; `status(entry) -> str` (`"ready"|"no_key"|"unconfigured"`); `build_model(entry) -> ReasoningModel`; `save_endpoint(id, label, base_url, model, api_key_env=None)`. Module global `_CONFIG: Path` (monkeypatchable in tests).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_registry.py
from chansu.reasoning import registry
from chansu.reasoning.adapter import ClaudeReasoningModel
from chansu.reasoning.openai_compatible import OpenAICompatibleReasoningModel


def test_builtins_present_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    ids = {e.id for e in registry.load_registry()}
    assert {"claude", "openai", "local"} <= ids


def test_status_reflects_env(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    entries = {e.id: e for e in registry.load_registry()}
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert registry.status(entries["claude"]) == "no_key"
    assert registry.status(entries["openai"]) == "no_key"
    assert registry.status(entries["local"]) == "ready"          # keyless + has base_url
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert registry.status(entries["claude"]) == "ready"


def test_build_model_types(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    entries = {e.id: e for e in registry.load_registry()}
    assert isinstance(registry.build_model(entries["claude"]), ClaudeReasoningModel)
    assert isinstance(registry.build_model(entries["local"]), OpenAICompatibleReasoningModel)


def test_save_and_load_endpoint_round_trips(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    registry.save_endpoint("perplexity", "Perplexity", "https://api.perplexity.ai", "sonar", "PPLX_API_KEY")
    entries = {e.id: e for e in registry.load_registry()}
    assert "perplexity" in entries and entries["perplexity"].base_url == "https://api.perplexity.ai"


def test_local_base_url_override(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "_CONFIG", tmp_path / "models.local.json")
    registry.save_endpoint("local", "Local (Qwen)", "http://192.0.2.10:11434/v1", "qwen2.5:14b-instruct")
    local = {e.id: e for e in registry.load_registry()}["local"]
    assert local.base_url == "http://192.0.2.10:11434/v1"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_registry.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the implementation**

```python
# chansu/reasoning/registry.py
"""The set of available reasoning backends and how to build each. Generic; no compound knowledge.
Secrets live in the environment (never here); non-secret endpoint config (labels, URLs, model names)
persists to a gitignored local file so user-added and edited endpoints survive restarts."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from .adapter import ClaudeReasoningModel, ReasoningModel
from .openai_compatible import OpenAICompatibleReasoningModel

# repo-root/data/models.local.json — gitignored; non-secret config only (never a key)
_CONFIG = Path(__file__).resolve().parents[2] / "data" / "models.local.json"


@dataclass
class ModelEntry:
    id: str
    label: str
    kind: str                        # "claude" | "openai_compatible"
    model: str
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    builtin: bool = False


_BUILTIN = [
    ModelEntry("claude", "Claude", "claude", "claude-opus-4-8", api_key_env="ANTHROPIC_API_KEY", builtin=True),
    ModelEntry("openai", "ChatGPT", "openai_compatible", "gpt-4o",
               base_url="https://api.openai.com/v1", api_key_env="OPENAI_API_KEY", builtin=True),
    ModelEntry("local", "Local", "openai_compatible", "qwen2.5:14b-instruct",
               base_url="http://localhost:11434/v1", api_key_env=None, builtin=True),
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
        entries.append(ModelEntry(id=eid, label=cfg["label"], kind="openai_compatible", model=cfg["model"],
                                  base_url=cfg["base_url"], api_key_env=cfg.get("api_key_env")))
    return entries


def status(entry: ModelEntry) -> str:
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
```

- [ ] **Step 4: Add the gitignore entry**

Append to `.gitignore`:
```text
# user-added model endpoints (non-secret config; kept local)
data/models.local.json
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_registry.py -q`
Expected: PASS. (The shipped suite has since grown; the code is authoritative per the header note.)

- [ ] **Step 6: Commit** (get Luke's OK)

```bash
git add chansu/reasoning/registry.py tests/test_registry.py .gitignore
git commit -m "feat(reasoning): model registry (built-in + user endpoints, env-only keys)"
```

---

### Task 3: Comparison README builder

**Files:**
- Create: `chansu/comparison.py`
- Test: `tests/test_comparison.py`

**Interfaces:**
- Consumes: `report.render_memo`, a `{label: DesignReasoning|None}` mapping, `DesignReasoning` shape (`available`, `narrative`, `rationales: {(liability, strategy_id): text}`, `checks`, `note`).
- Produces: `build_comparison_readme(compound, mol, result, reasonings: dict) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_comparison.py
from chansu.comparison import build_comparison_readme
from chansu.core.loaders import load_compound, load_strategies, to_mol
from chansu.core.pipeline import design
from chansu.reasoning.design_reasoning import DesignReasoning


def _fixture():
    compound = load_compound("bufalin")
    mol = to_mol(compound)
    result = design(compound, mol, load_strategies())
    return compound, mol, result


def test_readme_includes_each_model_and_declines():
    compound, mol, result = _fixture()
    reasonings = {
        "Claude": DesignReasoning(model_name="claude", available=True, narrative="A synthesis paragraph."),
        "Local": DesignReasoning(model_name="local", available=False, note="backend unavailable"),
    }
    md = build_comparison_readme(compound, mol, result, reasonings)
    assert "# Chansu design memo" in md
    assert "### Claude" in md and "A synthesis paragraph." in md
    assert "### Local" in md and "No reasoning" in md   # decline shown, not hidden
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_comparison.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the implementation**

```python
# chansu/comparison.py
"""Assemble a downloadable README comparing each model's reasoning over the same deterministic design.
Pure text; reuses report.render_memo and invents no claim. Declines are shown as declines (§6).
Reusable by the UI and a future MCP surface."""
from __future__ import annotations

from .report import render_memo


def build_comparison_readme(compound, mol, result, reasonings: dict) -> str:
    """``reasonings``: ``{model_label: DesignReasoning | None}``. Renders the deterministic memo once
    (model-agnostic), then each model's reasoning section (or its honest decline)."""
    out = [f"# Chansu design memo — {compound.name}", "", render_memo(compound, mol, result, None), "",
           "## Model reasoning (comparison)"]
    for label, reasoning in reasonings.items():
        out += ["", f"### {label}"]
        if reasoning is None or not reasoning.available:
            note = getattr(reasoning, "note", None) or "not run"
            out.append(f"_No reasoning: {note}._")
            continue
        if reasoning.narrative:
            out.append(reasoning.narrative.strip())
        for (liability, strategy_id), text in reasoning.rationales.items():
            out.append(f"- **{liability} / {strategy_id}:** {text.strip()}")
        cleared = sum(1 for c in reasoning.checks if c.passed)
        out.append(f"_Checks: {cleared}/{len(reasoning.checks)} cleared._")
    return "\n".join(out)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_comparison.py -q`
Expected: PASS.

- [ ] **Step 5: Commit** (get Luke's OK)

```bash
git add chansu/comparison.py tests/test_comparison.py
git commit -m "feat(reasoning): comparison README builder"
```

---

### Task 4: Registry access in state + connect-a-model UI

**Files:**
- Modify: `chansu/ui/state.py` (registry helpers)
- Create: `chansu/ui/models.py` (`render_model_setup`)
- Modify: `chansu/ui/app.py` (show the setup surface in the sidebar)
- Test: `tests/test_ui_models_import.py` (import smoke)

This task is build-and-verify-in-preview (Streamlit). Build to chansu-design; run `chansu-theme-review` before commit.

**Interfaces:**
- Produces (state): `model_entries() -> list[ModelEntry]` (cached, short TTL), `reasoning_model_for(entry)` (build via registry). Consumes `chansu.reasoning.registry`.
- Produces (UI): `render_model_setup() -> None`.

- [ ] **Step 1: Write the import-smoke test**

```python
# tests/test_ui_models_import.py
def test_render_model_setup_importable():
    from chansu.ui import models as ui_models
    assert hasattr(ui_models, "render_model_setup")
```

- [ ] **Step 2: Add registry helpers to `chansu/ui/state.py`**

```python
from ..reasoning import registry  # noqa: E402  (add near the other imports)


@st.cache_data(show_spinner=False, ttl=30)
def model_entries():
    """Registry entries with live status; short TTL so a newly-added endpoint or a just-set env key
    shows up without a restart. Returns a list of (entry, status) tuples."""
    return [(e, registry.status(e)) for e in registry.load_registry()]


def reasoning_model_for(entry):
    return registry.build_model(entry)
```

(Keep the existing `get_reasoning_model()` for now; the memo page will move to `model_entries` in Task 5.)

- [ ] **Step 3: Write `chansu/ui/models.py`**

```python
"""Screen fragment: connect-a-model setup. Shows each backend's status and lets the user edit an
endpoint or add a new one. Secrets are NEVER entered here — the panel only reports whether the env
key is present and links the user to set it. This module arranges and displays only (chansu-design)."""
from __future__ import annotations

import html

import streamlit as st

from ..reasoning import registry
from . import state

_STATUS = {
    "ready": ("var(--pass)", "ready"),
    "no_key": ("var(--high)", "key not set"),
    "unconfigured": ("var(--ink-3)", "unconfigured"),
}


def _status_row(entry, status):
    colour, label = _STATUS.get(status, ("var(--ink-3)", status))
    key_hint = (f" · set <code>{html.escape(entry.api_key_env)}</code> in .env" if status == "no_key" and entry.api_key_env else "")
    st.markdown(
        f"<div style='margin-top:6px'><span style='font-weight:600;color:var(--ink)'>{html.escape(entry.label)}</span> "
        f"<span style='font-family:var(--font-mono);font-size:11px;color:{colour}'>{label}</span>"
        f"<span class='cs-sub'>{key_hint}</span></div>"
        f"<div style='font-family:var(--font-mono);font-size:11px;color:var(--ink-3)'>{html.escape(entry.model)}"
        f"{' · ' + html.escape(entry.base_url) if entry.base_url else ''}</div>",
        unsafe_allow_html=True,
    )


def render_model_setup() -> None:
    st.markdown("<p class='cs-eyebrow'>Models</p>", unsafe_allow_html=True)
    st.markdown("<div class='cs-sub'>Keys live in your environment (.env), never in the app. Endpoints "
                "and model names are set here.</div>", unsafe_allow_html=True)
    for entry, status in state.model_entries():
        _status_row(entry, status)

    with st.expander("Edit or add an endpoint"):
        eid = st.text_input("Id", placeholder="local  (or a new slug like 'perplexity')")
        label = st.text_input("Label", placeholder="Local (Qwen)")
        base_url = st.text_input("Base URL", placeholder="http://<host>:11434/v1")
        model = st.text_input("Model", placeholder="qwen2.5:14b-instruct")
        api_key_env = st.text_input("API key env var (blank if none)", placeholder="OPENAI_API_KEY")
        if st.button("Save endpoint", type="primary", disabled=not (eid and base_url and model)):
            registry.save_endpoint(eid.strip(), (label or eid).strip(), base_url.strip(), model.strip(),
                                   (api_key_env.strip() or None))
            state.model_entries.clear()
            st.markdown(f"<div class='cs-pass'>Saved <b>{html.escape(eid)}</b>. Select it on the memo page.</div>",
                        unsafe_allow_html=True)
```

- [ ] **Step 4: Wire it into `chansu/ui/app.py`** — in `_sidebar()`, after the reasoning-depth control and before the About button:

```python
        st.divider()
        from chansu.ui.models import render_model_setup
        with st.expander("Models"):
            render_model_setup()
```

- [ ] **Step 5: Run the import smoke + full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all prior + the new smoke; `test_generic_engine_rule` green).

- [ ] **Step 6: Verify in the browser** (`chansu-ui`): the sidebar **Models** expander lists Claude / ChatGPT / Local with status chips (Claude/OpenAI show "key not set" until `.env` has the keys; Local shows "ready"). Edit the Local endpoint to your server, e.g. `http://<host>:11434/v1`, and save → it persists (check `data/models.local.json`). Console/logs clean.

- [ ] **Step 7: Run `chansu-theme-review`** on `chansu/ui/models.py`; fix findings.

- [ ] **Step 8: Commit** (get Luke's OK)

```bash
git add chansu/ui/models.py chansu/ui/app.py chansu/ui/state.py tests/test_ui_models_import.py
git commit -m "feat(ui): connect-a-model setup (status + edit/add endpoints, env-only keys)"
```

---

### Task 5: Reasoning-page redesign — multi-select, run-all, side-by-side, expanded checks

**Files:**
- Modify: `chansu/ui/memo.py` (`render_memo_tab` reasoning section)
- Modify: `chansu/ui/app.py` (memo tab no longer needs the single `model` arg)

Build-and-verify. Reuse the existing `_render_checks`, `_synthesis`, `_liability_block` helpers per model. The deterministic `_memo_body` is unchanged.

**Interfaces:**
- Consumes: `state.model_entries()`, `state.reasoning_model_for(entry)`, `reason_over_design`, the existing memo render helpers.

- [ ] **Step 1: Replace the single-model control** in `render_memo_tab` with a multi-select + run:

```python
    ready = [(e, s) for (e, s) in state.model_entries() if s == "ready"]
    labels = [e.label for e, _ in ready]
    st.markdown("<p class='cs-eyebrow'>Reasoning models</p>", unsafe_allow_html=True)
    default = [labels[0]] if labels else []
    picked = st.multiselect("Models", labels, default=default, label_visibility="collapsed",
                            help="Independent viewpoints. Agreement corroborates; disagreement flags where to look.")
    run = st.button("Run reasoning", type="primary", disabled=not picked)
    if run:
        chosen = [e for e, _ in ready if e.label in picked]
        for entry in chosen:
            key = f"reasoning:{compound.id}:{depth}:{entry.id}"
            with st.spinner(f"Running {entry.label}"):
                try:
                    st.session_state[key] = reason_over_design(
                        compound, result, state.reasoning_model_for(entry), depth=depth)
                except ReasoningError as exc:
                    st.session_state[key] = None
                    st.session_state[key + ":err"] = str(exc)
```

- [ ] **Step 2: Render results side by side** — replace the single `_render_checks` / `_synthesis` block with per-model columns:

```python
    active = [(e, s) for (e, s) in state.model_entries()
              if st.session_state.get(f"reasoning:{compound.id}:{depth}:{e.id}") is not None
              or st.session_state.get(f"reasoning:{compound.id}:{depth}:{e.id}:err")]
    if active:
        cols = st.columns(len(active))
        for col, (entry, _s) in zip(cols, active):
            with col:
                st.markdown(f"<div style='margin-top:8px'>{_prov_reason(entry.model)}</div>", unsafe_allow_html=True)
                reasoning = st.session_state.get(f"reasoning:{compound.id}:{depth}:{entry.id}")
                err = st.session_state.get(f"reasoning:{compound.id}:{depth}:{entry.id}:err")
                if err:
                    st.markdown(f"<div class='cs-declined'>Backend unavailable. {html.escape(err)}</div>", unsafe_allow_html=True)
                    continue
                _render_checks_expanded(reasoning)
                if reasoning.narrative:
                    st.markdown(sci(reasoning.narrative.strip()))
```

- [ ] **Step 3: Add `_render_checks_expanded`** — a fuller version of `_render_checks` that lists each check's outcome and reason (not just a count):

```python
def _render_checks_expanded(reasoning) -> None:
    checks = getattr(reasoning, "checks", None) or []
    passed = sum(1 for c in checks if c.passed)
    st.markdown(f"<div class='cs-sub'>{passed} of {len(checks)} reasoning calls cleared.</div>", unsafe_allow_html=True)
    rows = []
    for c in checks:
        if c.passed:
            rows.append(f"<div style='margin-top:4px;font-family:var(--font-mono);font-size:11px'>"
                        f"<span style='color:var(--pass)'>cleared</span> · {html.escape(c.label)}</div>")
        else:
            why = c.stop_reason + (f"/{c.category}" if c.category else "")
            rows.append(f"<div style='margin-top:4px'><span class='cs-declined'>declined · {html.escape(why)}</span>"
                        f"<span style='font-family:var(--font-mono);font-size:11px;color:var(--ink-3);margin-left:8px'>{html.escape(c.label)}</span></div>")
    st.markdown("".join(rows), unsafe_allow_html=True)
```

- [ ] **Step 4: Update `app.py`** — `render_memo_tab(compound, mol, result)` (drop the `model` arg; the page pulls models from state). Remove the now-unused `state.get_reasoning_model()` call.

- [ ] **Step 5: Verify in the browser** (with `ANTHROPIC_API_KEY` + `OPENAI_API_KEY` in `.env`, Ollama serving):
  - The memo page shows a **model multi-select** (Claude / ChatGPT / Local) defaulting to Claude, and a **"Run reasoning"** button.
  - Pick **all three**, Run → three columns render, each tagged `[reasoning · <model>]`, each with its expanded checks. A model that declines shows a calm decline, the others still render.
  - The deterministic memo below is unchanged.
  - Console/logs clean.

- [ ] **Step 6: `chansu-theme-review`** on `chansu/ui/memo.py`; fix findings. Run `.venv/bin/python -m pytest -q` (green).

- [ ] **Step 7: Commit** (get Luke's OK)

```bash
git add chansu/ui/memo.py chansu/ui/app.py
git commit -m "feat(ui): multi-model reasoning — select, run-all, side-by-side, expanded checks"
```

---

### Task 6: README download

**Files:**
- Modify: `chansu/ui/memo.py` (download button)

- [ ] **Step 1: Add a download control** below the per-model columns, when at least one model has run:

```python
    ran = {e.label: st.session_state.get(f"reasoning:{compound.id}:{depth}:{e.id}")
           for e, _ in state.model_entries()
           if st.session_state.get(f"reasoning:{compound.id}:{depth}:{e.id}") is not None}
    if ran:
        from ..comparison import build_comparison_readme
        st.download_button("Download comparison (README.md)",
                           data=build_comparison_readme(compound, mol, result, ran),
                           file_name=f"{compound.id}-design-comparison.md", mime="text/markdown")
```

- [ ] **Step 2: Verify in the browser** — after running ≥1 model, the download button appears; the downloaded `.md` contains the deterministic memo + each model's section (or decline). Run `.venv/bin/python -m pytest -q` (green).

- [ ] **Step 3: Commit** (get Luke's OK)

```bash
git add chansu/ui/memo.py
git commit -m "feat(ui): download the model comparison as a README"
```

---

## Live smoke (manual, after the build)

With `.env` holding `ANTHROPIC_API_KEY` + `OPENAI_API_KEY` (Luke sets them; never read here) and Ollama serving on `http://<host>:11434/v1`: on the memo page select every model, Run, and confirm Claude + ChatGPT + Qwen each produce a section or an honest decline, then download the README. (Producer B's model picker wiring to this registry is a thin follow-up in that feature, out of scope here.)

## Self-review

**Spec coverage:** adapter → Task 1; registry + env keys + gitignored config → Task 2; connect surface → Task 4; multi-select + run-all + side-by-side + expanded checks → Task 5; README export → Tasks 3 + 6; deterministic memo untouched → Tasks 5 (unchanged `_memo_body`). Producer B is a documented follow-up. Covered.

**Placeholder scan:** no TBD/TODO; each code step is complete. The `local` default `http://localhost:11434/v1` is intentional (real IP set in-app, gitignored).

**Type consistency:** `ModelEntry(id, label, kind, model, base_url, api_key_env, builtin)`, `load_registry()`, `status()`, `build_model()`, `save_endpoint()`, `OpenAICompatibleReasoningModel(model, base_url, api_key_env, ...)`, `build_comparison_readme(compound, mol, result, reasonings)` — used consistently across tasks and the UI.

## Out of scope (this plan)

Parallel model execution (sequential MVP); in-app raw-key entry; Producer B's full build; the MCP connector; multi-user/hosted; changing the deterministic memo.

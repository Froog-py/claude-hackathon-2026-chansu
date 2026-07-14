# Chansu — multi-model reasoning (design)

Design spec for feature #2: make the reasoning **layer** model-pluggable — run Claude, ChatGPT, or a
local model (or all of them), compare side by side, export the comparison, and let a user connect
their own model. Companion to [`day5-streamlit-ui-design.md`](day5-streamlit-ui-design.md); reuses the
chansu-design system.

## Status and scope

Additive. The **deterministic memo is unchanged** and remains the floor; only the reasoning layer on
top becomes multi-model. Producer B (research-log structuring, a later feature) reuses this same
layer. Not in this pass: parallel model execution, in-app raw-key entry, the MCP connector, multi-user.

**The good news, restated:** the architecture already supports this. [`ReasoningModel`](../chansu/reasoning/adapter.py)
is a provider-neutral Protocol, [`reason_over_design`](../chansu/reasoning/design_reasoning.py) depends
only on the interface, and the `[reasoning · <model>]` provenance tag already names whatever model is
behind it. Feature #2 adds one adapter, a registry, a redesigned page, and an export.

## Problem

Today there is one hardcoded backend: a "Run Claude reasoning" button wired to a single
`ClaudeReasoningModel`. We want: pick any of Claude / OpenAI / local (one or several at once), run, see each
model's analysis side by side with its own honest checks, download the comparison, and add a new
model the same way — **securely** (keys never in the app or the repo).

**Why multi-model matters (beyond refusal-handling):** independent models are independent
viewpoints. Agreement across Claude, ChatGPT, and a local model *corroborates* a conclusion;
disagreement marks exactly where a single model should not be trusted. This is triangulation, and it
is valuable even when no model declines — the goal is not to route around refusals, it is to not rely
on one viewpoint.

## Architecture — what exists vs. what's new

- **Exists:** the `ReasoningModel` Protocol, `ClaudeReasoningModel`, `EchoReasoningModel`,
  `reason_over_design()` (model-agnostic), the reasoning-checks panel, and provenance tags.
- **New:**
  1. `OpenAICompatibleReasoningModel` — one adapter for OpenAI **and** Ollama **and** any future
     `/v1/chat/completions` endpoint.
  2. A **model registry** — built-in providers + user-added endpoints; secrets from env, config
     non-secret.
  3. The **reasoning-page redesign** — model multi-select + "Run reasoning" + side-by-side compare +
     expanded checks.
  4. **README export** of the comparison.

---

## 1. The provider adapter — `OpenAICompatibleReasoningModel`

A second concrete backend beside `ClaudeReasoningModel`, implementing the same `ReasoningModel`
Protocol (`complete` / `stream` / `name`). One class covers **ChatGPT, the local Qwen (Ollama), and
any endpoint a user adds**, because all speak OpenAI-style `/v1/chat/completions`.

```python
OpenAICompatibleReasoningModel(
    model: str,                     # e.g. "gpt-4o" or "qwen2.5:14b-instruct"
    base_url: str,                  # "https://api.openai.com/v1" or "http://<win-ip>:11434/v1"
    api_key_env: Optional[str],     # env var holding the key ("OPENAI_API_KEY"); None for keyless local
    default_max_tokens: int = 2048,
)
```

- Uses the `openai` SDK with `base_url` overridden (it targets OpenAI, Ollama, and vLLM unchanged), or
  `httpx` if we want zero new deps — decided at build time; the mapping is the same either way.
- **Reads the key from `os.environ[api_key_env]` at call time** (the client is rebuilt if the key
  changes), and never persists or logs it. A missing key raises `ReasoningError` (honest failure),
  surfaced as "not configured", not a crash.
- Maps `ReasoningRequest` → chat messages (system + messages) and the response → `ReasoningResponse`
  (`text`, `stop_reason`, `usage`). A refusal / content-filter stop is mapped to the honest
  `stop_reason` the memo already understands, exactly like the Claude adapter.
- `name` returns the model id, so the provenance tag reads `[reasoning · gpt-4o]` /
  `[reasoning · qwen2.5:14b-instruct]` with no hardcoded vendor.

---

## 2. The model registry — `chansu/reasoning/registry.py`

The list of available backends and how to build each one. Generic; no compound knowledge.

```python
@dataclass
class ModelEntry:
    id: str                 # "claude" | "openai" | "local" | a user slug
    label: str              # "Claude" | "ChatGPT" | "Local (Qwen)"
    kind: str               # "claude" | "openai_compatible"
    model: str
    base_url: Optional[str] = None      # openai_compatible only
    api_key_env: Optional[str] = None   # env var name; None = keyless
    builtin: bool = False
```

- **Built-in entries** (defaults): `claude` (`ANTHROPIC_API_KEY`), `openai` (`OPENAI_API_KEY`,
  default model), `local` (base_url + model, keyless).
- **User-added endpoints** persist to a **gitignored** `data/models.local.json` — non-secret only
  (label, base_url, model, `api_key_env` **name**). The key itself is never written here; it stays in
  the environment.
- `build_model(entry) -> ReasoningModel` constructs the right adapter.
- `status(entry) -> str` computed at runtime: `ready` (key present / endpoint set), `no_key`
  (`api_key_env` unset), or `unconfigured` — this drives the connect panel and disables un-ready models
  in the picker.

---

## 3. Connect-a-model surface (setup)

A **"Models"** area (a sidebar expander or a small settings section) where the three provider types are
set up — Claude, OpenAI, local — and new ones added.

- Per entry: **label + status chip** (`ready` `--pass` / `no_key` `--high` / `unconfigured` muted) and,
  for editable entries, **config fields** (base_url + model for local/added; model for OpenAI).
- **Secrets are never entered here.** For a `no_key` entry the panel shows a one-line instruction
  ("Set `OPENAI_API_KEY` in your environment or a `.env` file, then reload") and a detected/not status.
  This is the secure answer to "do users type keys in-app?" — no; the app only *reads* env.
- **Add a model:** base_url + model + optional `api_key_env` name → appended to the gitignored config.
  This is the "plug in your own AI" moment; because it is OpenAI-compatible it covers Perplexity,
  another local model, etc.

---

## 4. The reasoning page (redesign)

Replaces the single "Run Claude reasoning" button on the Design-memo screen.

- **Model multi-select** — a multiselect of every `ready` entry (Claude / ChatGPT / Local / added);
  select one, several, or all of them to run them together. Default selection = **Claude**. Un-ready
  models are not offered here; their status is shown in the connect-a-model panel.
- A generic **"Run reasoning"** button (no vendor in the label).
- On run, for each selected model: `reason_over_design(compound, result, build_model(entry), depth)`
  (the function is already model-agnostic) → one `DesignReasoning` per model.
- **Side-by-side render** (Streamlit columns, wrapping on narrow widths): per model, its synthesis +
  per-strategy rationales + its checks panel, each headed by the `[reasoning · <model>]` tag.
- **Expanded checks:** for each model, list *which* checks cleared and why — `cleared · <label>` in
  `--pass`, `declined · <stop_reason>/<category> · <label>` in the calm `.cs-declined` register — not
  just a count. A model that declines is shown declining; the deterministic memo below loses nothing.
- The **deterministic memo stays the floor**, rendered once (model-agnostic), unchanged.

**Design note (the demo's best moment):** the same prompt makes models behave differently, and on a
toxin like the flagship, Claude may decline where a local model answers. That is the trust boundary
made visible, not a bug. The compare view styles declines as *principled* (calm, cited stop-reason),
never as errors.

---

## 5. Run-all mechanics

- Selected models run **sequentially** (Streamlit is synchronous) with a spinner per model ("Running
  <label>…"). Parallel execution is a future optimization, not MVP.
- Each result is cached in `session_state` keyed by `(compound.id, depth, entry.id)`, so switching the
  view or re-selecting a model does not re-call it.
- **Per-model isolation:** one model erroring or declining never sinks the others — each is wrapped so
  its column shows an honest per-model status while the rest render.

---

## 6. README export

A **"Download comparison (README.md)"** button builds a markdown document from the same data already on
screen (no new claims):

- Compound header (name, identifiers).
- The deterministic design: scoring rubric + ranked candidates with property deltas and provenance
  tags (reuse `report.render_memo` content).
- Per selected model: its synthesis + rationales + checks, each provenance-tagged.
- The honest-limits note. Declines are included as declines.

Implemented as a pure function (`build_comparison_readme(compound, result, {entry_id: DesignReasoning})
-> str`) so it is unit-testable and reusable by a future MCP surface.

---

## 7. Producer B hook

Producer B (research-log structuring, a later feature) uses **this same registry**: default Claude,
others selectable. This spec only ensures the registry + adapters are shaped for that reuse; B itself
is out of scope here.

---

## 8. Security and trust boundary

- **Keys from the environment only.** Never stored, logged, committed, or entered in the app. The app
  reads `os.environ[api_key_env]` at call time. Claude already works this way; the new adapter matches.
- **Config is non-secret** (labels, base URLs, model names) and lives in a gitignored local file.
- **Every model stays provenance-tagged** (`[reasoning · <model>]`); declines render honestly; the
  deterministic memo is the floor regardless of any model.
- Non-Claude models get the **same system prompt** (ground-don't-predict, no fabricated citations, no
  outcome forecasts). We cannot *guarantee* a third-party model obeys, so the provenance tag + the
  deterministic floor remain the safety net — stated honestly, not hidden.

---

## 9. Testing (minimal, per Luke)

- **Adapter mapping** — `OpenAICompatibleReasoningModel` request/response mapping against an injected
  fake client (no network), mirroring the Claude adapter's mock tests: text, stop_reason, usage,
  missing-key → `ReasoningError`.
- **Registry** — `status()` for key-present / key-absent / unconfigured; add-endpoint round-trip
  through the gitignored config.
- **README export** — `build_comparison_readme` includes each model's section + provenance and omits
  nothing that rendered.
- **Live smoke (manual, opt-in):** with `OPENAI_API_KEY` set (your key, never read by me) and the
  Windows Qwen endpoint reachable, run all three and confirm each responds or declines honestly.

---

## 10. Demo setup (environment)

- **Chansu runs on the Mac.**
- **Claude:** `ANTHROPIC_API_KEY` in `.env`.
- **OpenAI:** `OPENAI_API_KEY` in `.env`; default model TBD (gpt-4o / gpt-5 / o-series — Luke to pick).
- **Local Qwen (Ollama on the Windows 11 PC):** on Windows set `OLLAMA_HOST=0.0.0.0` and restart
  Ollama, allow TCP 11434 through the firewall; Chansu targets `http://<windows-lan-ip>:11434/v1`,
  model `qwen2.5:14b-instruct`.

---

## 11. Build order

1. `OpenAICompatibleReasoningModel` + mock mapping tests.
2. `registry.py` (entries, `build_model`, `status`) + gitignored config + tests.
3. Connect-a-model settings surface (chansu-design; `chansu-theme-review` before commit).
4. Reasoning-page redesign: multi-select + "Run reasoning" + side-by-side + expanded checks.
5. Run-all mechanics + per-model session caching.
6. `build_comparison_readme` + download button + test.
7. Live smoke (OpenAI key + Windows Qwen), then wire Producer B's model picker to the registry (thin).

Each step is independently checkable.

---

## 12. Out of scope (this pass)

Parallel model execution; in-app raw-key entry; Producer B's full build; the MCP connector;
multi-user/hosted; changing the deterministic memo.

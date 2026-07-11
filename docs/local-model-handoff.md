# Local-model handoff spec

> **For the separate Claude Code agent on the Windows PC.** You have no other context on this
> project, and you don't need it. Your entire job is described below: stand up a **local model**
> that can serve as an alternate reasoning backend behind a fixed Python interface. This is a
> **stretch goal** (see the last section) — it must not touch or risk the main project.

---

## 1. What the system is

**DeRisk** is a medicinal-chemistry tool: given a compound, it grounds the compound in
literature, reasons about which parts of the molecule matter, and generates citation-backed
hypotheses for modifying it. The reasoning is done by a language model; the numbers are done
deterministically by RDKit. The production reasoning model is **Claude**.

The reasoning layer sits behind a small **model-adapter interface** so a different model can
drive it. **Your local model is one such swappable backend.** You will implement a class that
conforms to the interface, backed by a locally-served model, and prove it works with a smoke
test. You do **not** touch anything else in the codebase.

---

## 2. The exact interface your backend must conform to

The contract is defined in [`derisk/reasoning/adapter.py`](../derisk/reasoning/adapter.py).
Read that file — it is the single source of truth. Summary below.

### The call signature

Implement a class satisfying the `ReasoningModel` protocol:

```python
class ReasoningModel(Protocol):
    def complete(self, request: ReasoningRequest) -> ReasoningResponse: ...
    def stream(self, request: ReasoningRequest) -> Iterator[str]: ...
```

The easiest path is to subclass `BaseReasoningModel` (it gives you a default `stream` that
wraps `complete`, so you only implement `complete`):

```python
from derisk.reasoning.adapter import (
    BaseReasoningModel, ReasoningRequest, ReasoningResponse, ToolCall, Usage, ReasoningError,
)

class LocalReasoningModel(BaseReasoningModel):
    def __init__(self, base_url: str, model: str): ...
    def complete(self, request: ReasoningRequest) -> ReasoningResponse: ...
```

### Input shape — `ReasoningRequest`

| Field | Type | Meaning |
|---|---|---|
| `system` | `str` | System prompt (instructions + provenance rules). |
| `messages` | `list[Message]` | Conversation. `Message(role, content)`, role is `"user"` or `"assistant"`. |
| `tools` | `list[ToolSpec]` | Available tools. `ToolSpec(name, description, input_schema)` — `input_schema` is JSON Schema. May be empty. |
| `max_tokens` | `int` | Output cap (default 4096). |
| `temperature` | `float` | Default `0.0` (deterministic scientific reasoning). |
| `stop_sequences` | `list[str]` | Optional stop strings. |

### Output shape — `ReasoningResponse`

| Field | Type | Meaning |
|---|---|---|
| `text` | `str` | The model's text output. |
| `tool_calls` | `list[ToolCall]` | `ToolCall(id, name, arguments)`, `arguments` is a dict. Empty if none. |
| `stop_reason` | `str` | `"end_turn"` \| `"tool_use"` \| `"max_tokens"`. |
| `usage` | `Usage \| None` | `Usage(input_tokens, output_tokens)` if available. |
| `raw` | `Any` | The backend-native payload, for debugging only. |

### Tool calling

If `request.tools` is non-empty, advertise them to the model. When the model asks to call a
tool, return the calls in `response.tool_calls` and set `stop_reason="tool_use"` (do not
execute them — the core does that and sends results back as the next turn). If your model or
serving stack cannot do function calling, you may return an empty `tool_calls` and rely on
text — but see requirements below: tool calling is expected to be supported.

### Errors and streaming

- On any failure (connection, timeout, bad response) **raise `ReasoningError`** (or
  `ReasoningTimeout`). **Never** return partial or fabricated text as if it were complete —
  the trust boundary depends on honest failure.
- `stream(request)` yields text chunks as they arrive. If your stack can't stream, the
  `BaseReasoningModel` default (yield the full `complete().text` once) is acceptable.

---

## 3. Requirements the model must meet

State these as hard requirements; pick any model that satisfies them and fits the hardware.

- **Multi-step scientific reasoning** over retrieved literature: it must follow a structured
  system prompt, reason over distilled paper records, and produce structured, grounded output
  without drifting into invented facts. Prefer instruction-tuned models with strong reasoning.
- **Context window ≥ 32k tokens** (bigger is better). The prompt carries a system prompt plus
  several distilled literature records plus instructions. 8k is too small; 32k–128k is the
  target range.
- **Function / tool calling support** in the serving stack (the adapter passes tool specs).
  If you must choose between reasoning quality and tool calling, favor reasoning quality and
  note the limitation — the core can degrade to a text-only path.
- **JSON-faithful output** — able to emit well-formed structured output on request.

You choose the specific model. Do not pick one before answering §4.

---

## 4. Answer these hardware questions FIRST

Model size is gated by hardware. Check **before** choosing a model:

1. **GPU VRAM** — how many GB? (e.g. `nvidia-smi`.) This sets the largest model + quantization
   you can run at usable speed.
2. **System RAM** — how many GB? (CPU-offload fallback / larger context.)
3. **GPU model / compute capability** — determines which runtimes and quant formats work.
4. **Disk free** — model weights are large (a 32B model at 4-bit is ~20 GB).

Rule of thumb (4-bit quantized, leave headroom for context): ~8 GB VRAM → 7–8B; ~16 GB →
13–14B; ~24 GB → 32B; more → larger. When unsure, size down — a smaller model that runs is
worth more than a big one that thrashes.

---

## 5. How to serve it locally + endpoint shape

Serve the model behind an **OpenAI-compatible `/v1/chat/completions` HTTP endpoint** — the
common denominator across local runtimes:

- **Ollama** (`ollama serve`, `http://localhost:11434/v1`), **llama.cpp** (`llama-server`),
  **vLLM**, or **LM Studio** all expose this shape. Any is fine.
- Your `LocalReasoningModel.complete` maps `ReasoningRequest` → the chat-completions request:
  - `request.system` → a `{"role": "system", ...}` message prepended to `request.messages`.
  - `request.tools` → the endpoint's `tools` array (OpenAI function-calling schema; each
    `ToolSpec.input_schema` is already JSON Schema).
  - `max_tokens`, `temperature`, `stop_sequences` map directly.
- Map the response back: `choices[0].message.content` → `text`; `tool_calls` →
  `list[ToolCall]`; `finish_reason` → `stop_reason` (`"stop"`→`"end_turn"`,
  `"tool_calls"`→`"tool_use"`, `"length"`→`"max_tokens"`); `usage` → `Usage`.

Keep the base URL and model name configurable (constructor args or env vars), not hard-coded.

---

## 6. How to verify the integration

Two checks, in order.

**A. Interface conformance (no model needed).** Confirm the interface imports and a trivial
backend round-trips:

```python
from derisk.reasoning.adapter import EchoReasoningModel, ReasoningRequest, Message, ReasoningModel
m = EchoReasoningModel()
assert isinstance(m, ReasoningModel)  # runtime-checkable protocol
r = m.complete(ReasoningRequest(system="s", messages=[Message("user", "ping")]))
assert r.text == "[echo] ping" and r.stop_reason == "end_turn"
print("interface OK")
```

**B. Real backend smoke test.** With your model served, run a real reasoning call and a real
tool call:

```python
from derisk.reasoning.adapter import ReasoningRequest, Message, ToolSpec
model = LocalReasoningModel(base_url="http://localhost:11434/v1", model="<your-model>")

# 1) plain reasoning
resp = model.complete(ReasoningRequest(
    system="You are a medicinal chemist. Answer in one sentence.",
    messages=[Message("user", "Why does capping a hydroxyl as an ester change solubility?")],
))
assert resp.text.strip()
print("reasoning OK:", resp.text[:120])

# 2) tool calling
resp = model.complete(ReasoningRequest(
    system="Use the tool to look up a property when asked.",
    messages=[Message("user", "Get the molecular weight of the parent compound.")],
    tools=[ToolSpec("get_mw", "Molecular weight of the current compound",
                    {"type": "object", "properties": {}, "required": []})],
))
assert resp.stop_reason in ("tool_use", "end_turn")
print("tool path OK:", resp.stop_reason, resp.tool_calls)

# 3) honest failure
try:
    LocalReasoningModel(base_url="http://localhost:9/v1", model="x").complete(
        ReasoningRequest(system="", messages=[Message("user", "hi")]))
    print("FAIL: should have raised ReasoningError")
except Exception as e:
    print("error path OK:", type(e).__name__)
```

Pass criteria: interface conformance passes; a real call returns non-empty text; the tool
path returns a `tool_use` (or a clean `end_turn`); an unreachable endpoint raises
`ReasoningError`.

---

## 7. This is a stretch goal — do not break the main project

- **Do not modify the core, the model-adapter interface, or the Claude-backed path.** The
  interface in `adapter.py` is the contract; treat it as read-only. If it genuinely needs a
  change, flag it — don't edit it unilaterally.
- Put your code in its **own module** (e.g. `derisk/reasoning/local_adapter.py`) and keep any
  heavy dependencies **optional** (import them inside your class, not at module top level) so
  the main project runs without them.
- The local backend **plugs in behind the interface or it doesn't ship.** Nothing on the
  critical path may depend on it. If it isn't ready, the project ships on Claude, unaffected.
- **Do not choose the model for the main team** — report the hardware findings (§4), the model
  you selected and why, how you served it, and the smoke-test output.

# Local model — Windows deployment report

Stretch-goal backend for Chansu on the CyberPowerPC Windows box. Production Claude path untouched. This document is the handoff for whoever wires the adapter into the app.

## Hardware (verified)

```text
NVIDIA GeForce RTX 5060 Ti, 16311 MiB, 591.86, 12.0
```

| Component | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 5060 Ti (Blackwell, sm_120) |
| VRAM | ~16 GB |
| Driver | 591.86 |
| RAM | 32 GB DDR5 (per handoff spec) |
| Disk | 2 TB SSD (per handoff spec) |

GPU visible via `nvidia-smi` before any model weights were downloaded.

## Runtime and model (this machine)

| Item | Value |
|---|---|
| Runtime | Ollama **0.31.2** (winget) |
| Model | **`qwen2.5:14b-instruct`** (~9.0 GB, Ollama registry id `7cdf5a0187d5`) |
| OpenAI-compatible base | `http://127.0.0.1:11434/v1` |
| Completions path | `POST {base}/chat/completions` |
| Bind | `127.0.0.1:11434` LISTENING only (verified via `netstat`; not LAN-exposed) |
| Context class | 14B Q4-class fits 16 GB VRAM with 32k+ context headroom |

## Env / constructor config

| Name | Required | Default | Meaning |
|---|---|---|---|
| `CHANSU_LOCAL_MODEL` | yes (or ctor `model=`) | _(none)_ | Served model id, e.g. `qwen2.5:14b-instruct` |
| `CHANSU_LOCAL_BASE_URL` | no | `http://127.0.0.1:11434/v1` | OpenAI-compatible API root (no trailing slash required); must be `http`/`https` |
| `CHANSU_LOCAL_ALLOW_REMOTE` | no | unset/false | If `1`/`true`/`yes`/`on`, skip **loopback host** allowlist only (`http`/`https` still required) |
| ctor `timeout_s` | no | `120.0` | HTTP timeout seconds |
| ctor `allow_remote` | no | from env | Explicit override of loopback host policy (scheme check always enforced) |

## Module surface (wiring facts)

| Fact | Value |
|---|---|
| Module | `chansu.reasoning.local_adapter` |
| Class | `LocalReasoningModel` |
| Bases | `BaseReasoningModel` → satisfies `ReasoningModel` protocol |
| Import | `from chansu.reasoning.local_adapter import LocalReasoningModel` |
| Contract file (read-only) | `chansu/reasoning/adapter.py` |
| Optional deps | **None** — stdlib `urllib` only; safe to import when Ollama is absent |
| Critical-path coupling | **None** — CLI/core do not import this module yet |
| Smoke script | `scripts/local_smoke_test.py` |

### Request mapping (`ReasoningRequest` → OpenAI chat-completions)

| Adapter field | Wire field |
|---|---|
| `system` | prepended `{"role":"system","content":...}` message |
| `messages[]` | `messages[]` with `role` / `content` |
| `tools[]` | `tools[]` as `{"type":"function","function":{"name","description","parameters": input_schema}}` |
| (when tools non-empty) | `tool_choice: "auto"` |
| `max_tokens` | `max_tokens` |
| `temperature` | `temperature` |
| `stop_sequences` | `stop` (omitted if empty) |
| _(fixed)_ | `stream: false` |

### Response mapping (OpenAI → `ReasoningResponse`)

| Wire field | Adapter field |
|---|---|
| `choices[0].message.content` | `text` (`""` if null) |
| `choices[0].message.tool_calls[]` | `tool_calls[]` as `ToolCall(id, name, arguments=dict)` |
| `function.arguments` | JSON object (string decoded; invalid JSON → `ReasoningError`) |
| `finish_reason` `stop` | `stop_reason="end_turn"` |
| `finish_reason` `tool_calls` | `stop_reason="tool_use"` |
| `finish_reason` `length` | `stop_reason="max_tokens"` |
| `usage.prompt_tokens` / `completion_tokens` | `Usage.input_tokens` / `output_tokens` |
| full JSON body | `raw` |

Normalization:

- Parsed tool calls present + `end_turn` → promote to `tool_use`.
- `tool_use` claimed but zero parsed calls → demote to `end_turn`.

### Errors

| Condition | Exception |
|---|---|
| Non-`http`/`https` scheme (always) | `ReasoningError` |
| Non-loopback host without allow_remote | `ReasoningError` |
| HTTP redirect (any) | `ReasoningError` (redirects disabled) |
| Connection refused / DNS / transport | `ReasoningError` |
| Timeout (`TimeoutError` or URLError-wrapped timeout) | `ReasoningTimeout` |
| HTTP 4xx/5xx | `ReasoningError` with status + body snippet |
| Invalid / non-object JSON | `ReasoningError` |
| Response body > 16 MiB | `ReasoningError` |
| Missing `choices` / `message` | `ReasoningError` |

No partial text is returned on failure.

### Streaming

`stream()` inherited from `BaseReasoningModel`: single yield of `complete().text`. No native token streaming.

## Security controls in the client

1. **HTTP(S) only** — `file://` and other schemes rejected even when remote is allowed.
2. **Loopback allowlist** by default: host must be `127.0.0.1`, `localhost`, or `::1`.
3. **Redirects refused** — a local peer cannot 307/308 POST bodies off-machine.
4. **Response size capped** at 16 MiB.
5. **No API keys** in repo or adapter; Ollama local server needs none.
6. Stretch module is optional and isolated from Claude path / `adapter.py`.

## Smoke results (this machine)

### §6A — Interface conformance (no model)

```console
interface OK
```

### §6B — Real backend (`qwen2.5:14b-instruct`)

```console
reasoning OK: Capping a hydroxyl group as an ester typically decreases solubility in water due to the reduced hydrogen bonding capacit...
tool path OK: end_turn []
error path OK: ReasoningError Local model connection failed: [WinError 10061] No connection could be made because the target machine actively refused
```

Pass criteria: non-empty reasoning text; tool path `tool_use` **or** clean `end_turn`; unreachable port → `ReasoningError`.

## Known limitations (integrator-relevant)

1. **Tool calling reliability:** With `qwen2.5:14b-instruct` via Ollama, the §6B tool prompt returned `end_turn` and empty `tool_calls` despite `tools` + `tool_choice: auto`. Adapter advertises tools correctly; model may answer in text. Core text-only degrade path remains valid.
2. **Cold start:** First call after Ollama idle can be ~30–45 s (VRAM load); later calls are faster.
3. **Not production-selected:** This model/runtime pair is a working proof on 16 GB Blackwell hardware, not a team mandate.
4. **Not wired:** Nothing in CLI/core constructs `LocalReasoningModel` yet.

## Files in this PR

| File | Role |
|---|---|
| `chansu/reasoning/local_adapter.py` | `LocalReasoningModel` implementation |
| `scripts/local_smoke_test.py` | §6B smoke runner (env: `CHANSU_LOCAL_MODEL`) |
| `docs/local-model-windows-report.md` | This report |
| `.gitignore` | ignores `ollama_pull.log` |

**Unchanged:** `chansu/reasoning/adapter.py`, Claude path, core, CI.

## Toolchain (this PC)

| Tool | Status |
|---|---|
| Python 3.12.10 | Installed |
| uv | Installed |
| Git 2.55.0 | Installed |
| Ollama 0.31.2 | Installed; model pulled |
| Repo | git clone on branch `local-model-adapter` |

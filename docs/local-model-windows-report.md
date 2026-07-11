# Local model — Windows deployment report

Stretch-goal backend for Chansu on the CyberPowerPC Windows box. Production Claude path untouched.

## Hardware (verified)

```
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

## Runtime and model

| Item | Choice | Rationale |
|---|---|---|
| Runtime | **Ollama 0.31.2** (winget) | OpenAI-compatible `/v1/chat/completions`, recent Blackwell support, scriptable |
| Model | **qwen2.5:14b-instruct** (~9.0 GB) | 14B instruct class fits 16 GB VRAM with context headroom; strong reasoning + JSON; official Ollama registry |
| Endpoint | `http://127.0.0.1:11434/v1` | Bound to localhost only (`127.0.0.1:11434` LISTENING — not exposed to LAN) |

Env vars (optional):

- `CHANSU_LOCAL_BASE_URL` — default `http://127.0.0.1:11434/v1`
- `CHANSU_LOCAL_MODEL` — required at runtime (e.g. `qwen2.5:14b-instruct`)

## Toolchain on this PC

| Tool | Status |
|---|---|
| Python 3.12.10 | Installed (winget) |
| uv 0.11.28 | Installed via pip |
| Chansu venv | `uv sync` succeeded (RDKit + numpy) |
| Git | Not installed (admin prompt cancelled); repo obtained via public GitHub zip |
| Ollama | Installed and serving on localhost |

Repo path: `C:\Users\lukek\Projects\claude-hackathon-2026-chansu`  
Source: https://github.com/Froog-py/claude-hackathon-2026-chansu (public — no auth required)

## Files added (isolated stretch work)

| File | Purpose |
|---|---|
| `chansu/reasoning/local_adapter.py` | `LocalReasoningModel` — maps `ReasoningRequest` ↔ OpenAI chat-completions |
| `scripts/local_smoke_test.py` | Handoff §6B smoke test runner |

**Not modified:** `chansu/reasoning/adapter.py`, Claude path, core, CI.

## Smoke test output

### §6A — Interface conformance (no model)

```
interface OK
```

### §6B — Real backend

```
reasoning OK: Capping a hydroxyl group as an ester typically decreases solubility in water due to the reduced hydrogen bonding capacit
tool path OK: end_turn []
error path OK: ReasoningError Local model connection failed: [WinError 10061] No connection could be made because the target machine actively refused
```

Pass criteria met:

- Non-empty reasoning text on a medicinal-chemistry prompt
- Tool path returned acceptable `end_turn` (see limitations)
- Unreachable endpoint raised `ReasoningError` (honest failure)

Run locally:

```powershell
cd C:\Users\lukek\Projects\claude-hackathon-2026-chansu
$env:CHANSU_LOCAL_MODEL = "qwen2.5:14b-instruct"
.\.venv\Scripts\python.exe scripts\local_smoke_test.py
```

## Known limitations

1. **Tool calling:** On the smoke-test tool prompt, `qwen2.5:14b-instruct` via Ollama returned `end_turn` with empty `tool_calls` instead of `tool_use`. Reasoning and JSON output are strong; function-calling reliability may need prompt tuning, a different model tag, or explicit `tool_choice` in a future adapter revision. The core can degrade to text-only per handoff spec.
2. **Git not configured:** Repo is a zip extract, not a git clone. Install Git when ready for branch workflow (`local-model-adapter`).
3. **First inference latency:** ~45 s for first call (model load into VRAM); subsequent calls are faster.
4. **Stretch goal only:** Nothing on the critical path depends on this backend.

## Security notes

- Ollama listens on `127.0.0.1:11434` only (verified via `netstat`).
- No API keys, PATs, or secrets added to the repo.
- Model pulled from official Ollama registry (`qwen2.5:14b-instruct`).
- Install sources: winget (Git, Python, Ollama), python.org, GitHub (public repo zip).

## Recommendation for main team

This deployment proves the adapter contract works against a local OpenAI-compatible server on 16 GB Blackwell hardware. It does **not** choose the production local model for the team — report only. If tool calling becomes a hard requirement, evaluate models with stronger Ollama function-calling support or add `tool_choice: auto` and re-test.

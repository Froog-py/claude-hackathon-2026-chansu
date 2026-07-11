# Chansu — working rules for this repo

**Read [`PROJECT.md`](PROJECT.md) and [`BUILD_PLAN.md`](BUILD_PLAN.md) in full at the start
of every session.** They are the source of truth. [`CLAUDE_CODE_KICKOFF.md`](CLAUDE_CODE_KICKOFF.md)
has the standing rules for the week. This file is the short version.

## Non-negotiables

1. **Generic engine, compound-in-data (PROJECT.md §5).** No compound-specific knowledge in
   `chansu/` — nothing about bufalin, bufadienolides, steroids, lactones, or Na+/K+-ATPase in
   engine code. It all lives in `data/`. **Acceptance test:** adding a compound must require
   only new data. If you'd edit engine code to add a compound, the abstraction leaked — fix it.
   The rule is enforced by `tests/test_core.py`; keep it green.
2. **Trust boundary (PROJECT.md §6).** Claude reasons/retrieves; RDKit computes and validates
   every structure; the strategy library holds precedent. **Every output claim is
   provenance-tagged.** Never present a prediction as fact. **Never fabricate a citation.**
   Implement the two-way gate (flag, allow override with reason recorded). Prefer honest
   failure over inventing a strategy.
3. **Analog generation is the #1 risk (PROJECT.md §8).** Encoded transformations only;
   RDKit-sanitize everything; describe-and-highlight rather than emit a broken molecule.
4. **Scope is sacred.** Build only what's in `PROJECT.md`. Respect the NOT-THIS-WEEK list
   (§14). New ideas go in `SOMEDAY.md`, not into the build.
5. **Architect the layers; build only what's needed (PROJECT.md §10).** Core stays
   framework-agnostic. Reasoning sits behind the model-adapter interface. MCP and multi-model
   are architected-for, not built this week.

## Working cadence

Complements the global rules — kept here because this project is unusually verification-heavy
(the trust boundary, the acceptance test, the two spikes). Adapted from the
[andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) CLAUDE.md.

- **Goal-driven, with a real feedback loop.** Turn each task into a checkable success criterion
  and actually run it — a test, the CLI, an RDKit sanitization — before claiming it works.
  Evidence before assertions.
- **Think before coding; surface tradeoffs.** State assumptions, don't hide confusion, and
  offer 2–3 options on genuine forks (PROJECT.md §15) rather than silently picking.
- **Surgical changes.** Touch only what the task needs; match surrounding style; don't refactor
  adjacent code unasked. A rename or refactor changes no behavior.

## Environment

- **Python 3.12** in `.venv` (RDKit wheels lag the newest CPython — do not use 3.14).
- Set up: `uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python rdkit numpy pytest`
- Run demo: `.venv/bin/python -m chansu.cli`
- Test: `.venv/bin/python -m pytest -q`

## Git workflow

- `main` is the trunk; all work on **feature branches** off `main` via the `/start` skill.
  Do not commit build work directly to `main`.
- Never commit or push without asking. When work is done, use `/ship`.

## Layout

- `chansu/core/` — generic data model + deterministic logic (RDKit). No compound knowledge.
- `chansu/reasoning/` — model-adapter interface (Claude adapter lands Day 3).
- `data/` — compounds, transformations, config. Compound-specific knowledge lives here.
- `reference-material/` — literature workspace the pipeline reads from.
- `docs/` — the local-model handoff spec and [`gotchas.md`](docs/gotchas.md) (read before
  touching RDKit / generation / property / environment code).

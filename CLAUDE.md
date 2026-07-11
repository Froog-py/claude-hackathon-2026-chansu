# DeRisk — working rules for this repo

**Read [`PROJECT.md`](PROJECT.md) and [`BUILD_PLAN.md`](BUILD_PLAN.md) in full at the start
of every session.** They are the source of truth. [`CLAUDE_CODE_KICKOFF.md`](CLAUDE_CODE_KICKOFF.md)
has the standing rules for the week. This file is the short version.

## Non-negotiables

1. **Generic engine, compound-in-data (PROJECT.md §5).** No compound-specific knowledge in
   `derisk/` — nothing about bufalin, bufadienolides, steroids, lactones, or Na+/K+-ATPase in
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

## Environment

- **Python 3.12** in `.venv` (RDKit wheels lag the newest CPython — do not use 3.14).
- Set up: `uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python rdkit numpy pytest`
- Run demo: `.venv/bin/python -m derisk.cli`
- Test: `.venv/bin/python -m pytest -q`

## Git workflow

- `main` is the trunk; all work on **feature branches** off `main` via the `/start` skill.
  Do not commit build work directly to `main`.
- Never commit or push without asking. When work is done, use `/ship`.

## Layout

- `derisk/core/` — generic data model + deterministic logic (RDKit). No compound knowledge.
- `derisk/reasoning/` — model-adapter interface (Claude adapter lands Day 3).
- `data/` — compounds, transformations, config. Compound-specific knowledge lives here.
- `reference-material/` — literature workspace the pipeline reads from.
- `docs/` — including the local-model handoff spec.

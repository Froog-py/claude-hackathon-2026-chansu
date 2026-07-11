# Chansu

**A generic medicinal-chemistry engine.** Give it a natural compound and it grounds the
compound in literature, maps which parts of the molecule matter and why, and generates
**grounded, citation-backed hypotheses** for modifying it to fix a liability — toxicity,
poor distribution, poor solubility, rapid clearance, weak potency, and so on.

Built for the *Built with Claude: Life Sciences* hackathon (Build track). The reasoning is
powered by **Claude**; the deterministic chemistry is **RDKit**; precedent lives in a
curated **strategy library**. Bufalin is the flagship demo compound.

> **Source of truth:** [`PROJECT.md`](PROJECT.md) (what & why) and
> [`BUILD_PLAN.md`](BUILD_PLAN.md) (how & when). Read both before working on this repo.

## Two principles hold the project up

1. **Generic engine, compound-in-data.** No compound-specific knowledge lives in the engine
   (`chansu/`). Bufalin, its positions, its transformations — all of it is **data**
   (`data/`). *Adding a compound requires only new data, never an engine edit.* This is
   enforced by a test (`tests/test_core.py::test_generic_engine_rule_no_compound_knowledge_in_engine`).

2. **The trust boundary.** The tool is not an oracle. Claude retrieves and reasons; RDKit
   computes the numbers and validates every structure; the strategy library holds precedent.
   **Every output claim is provenance-tagged:** `[computed]`, `[literature — cited]`,
   `[hypothesis — needs wet-lab validation]`, `[out of scope]`. It never predicts binding,
   toxicity, or efficacy, never fabricates a citation, and declines to over-claim when
   nothing matches.

## Architecture (stratified layers — PROJECT.md §10)

| Layer | This week | Where |
|---|---|---|
| **Core library** — generic data model + deterministic RDKit logic | built | `chansu/core/` |
| **Reasoning layer** — pluggable behind a model-adapter interface (Claude in production) | interface only (adapter Day 3) | `chansu/reasoning/` |
| **Service layer** — MCP surface | architected, not built | — |
| **Interface** — Streamlit multi-screen | Day 5 | — |
| **Data / reference** — compounds, transformations, literature | built (data), pipeline Day 3 | `data/`, `reference-material/` |

## Quickstart

```bash
# Python 3.12 pinned (RDKit wheels lag the newest CPython)
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python rdkit numpy pytest

# Bufalin in -> computed properties + one validated analog out
.venv/bin/python -m chansu.cli

# Tests (includes the generic-engine acceptance test and the generation spike)
.venv/bin/python -m pytest -q
```

## Day-1 status (foundation + the two spikes)

- ✅ RDKit environment (2026.03.3) + smoke test.
- ✅ Bufalin from **PubChem CID 9547215** (not memory), loaded through the generic data model.
- ✅ Deterministic property module: MW, clogP, TPSA, HBD, HBA, rotatable bonds,
  Lipinski/Veber, Tanimoto-to-parent, synthetic-accessibility.
- ✅ **Generation spike**: one encoded transformation (O-acetylation) at one position (C3-OH)
  → a **valid**, RDKit-sanitized analog (bufalin 3-acetate).
- ✅ Model-adapter interface skeleton (`chansu/reasoning/adapter.py`) +
  [local-model handoff spec](docs/local-model-handoff.md).

See [`BUILD_PLAN.md`](BUILD_PLAN.md) for the day-by-day plan. The must-ship 80% lands Day 4.

# SOMEDAY — the scope-creep parking lot

New idea mid-sprint? Write it here and keep building the plan. Scope creep is the enemy
(BUILD_PLAN.md "Daily discipline"). Nothing here ships unless the must-ship 80% is solid.

## Stretch goals (from BUILD_PLAN.md — only after must-ship is rock-solid)

- **Thin second compound, added purely as data** — proves the generic model. Highest-value
  stretch; the acceptance test already guarantees no engine edits are needed.
- **3D viewer** (`stmol` / `py3Dmol`) in the Streamlit UI.
- **Agentic search-to-approve** into the Reference tab (design the approval gate honestly).
- **MCP server** exposing the core to external agents (architected for; not built this week).
- **Model-adapter wired to a second model** — the local-model handoff
  (`docs/local-model-handoff.md`) is this, running on a separate machine.

## Ideas captured during the build

- **Multi-match locators (Day 2, with generation hardening).** `resolve_position` currently
  takes `matches[0]` (first match wins). Fine for the flagship (bufalin's locators each resolve
  to exactly one atom) and inert Day 1, but a future compound whose locator SMARTS matches
  several equivalent sites would be silently modified at an arbitrary one — and the two-way gate
  would only evaluate that one atom. When generation is hardened Day 2+, either resolve all
  matches and generate/gate per-site, or emit an INFO flag when a locator matches >1 site.
  *(Surfaced by the Day-1 verification pass; not a Day-1 defect.)*
- **Enforce the LITERATURE-needs-a-Citation contract in code.** `models.py` documents that a
  `Provenance.LITERATURE` claim requires a real `Citation`, but nothing enforces it. Consider a
  render/emit path that makes a `[literature — cited]` output without a `Citation` impossible.
  *(The Day-1 CLI mislabel of a PubChem CID was fixed; this would prevent the class of bug.)*
- **Note:** the high-importance two-way gate (`importance_gate_flags` / `Flag.override`) is built
  and locked now though its data (the importance map) arrives Day 3 and the full gate is a Day-4
  deliverable. Kept deliberately (PROJECT.md §8 groups the gate into the generation surface Day 1
  spikes); it is generic and inert until the importance map exists.

# SOMEDAY — the scope-creep parking lot

New idea mid-sprint? Write it here and keep building the plan. Scope creep is the enemy
(BUILD_PLAN.md "Daily discipline"). Nothing here ships unless the must-ship 80% is solid.

## Stretch goals (from BUILD_PLAN.md — only after must-ship is rock-solid)

- **[#1 stretch] Claude Science MCP connector.** Expose Chansu's core as an MCP server that
  Claude Science calls via `host.mcp("server", "tool", **kwargs)` from its repl tool. Reference
  implementation: `github.com/bioteam/claude-science-hpc-integrations`. **Caveat:** Claude
  Science runs in remote sandbox containers, so a `localhost` MCP server is likely NOT reachable
  — a public/hosted MCP server is probably required. **Cheaper, unverified alternative:** its
  Python kernel may be able to `pip install chansu` and import the core directly (no hosted
  server). If we take that route, the Codex **wheel-omits-`data/`** finding (below) becomes live
  and must be fixed first. **Do NOT build until the Day-4 must-ship loop works**; keep the core
  clean/callable (PROJECT.md §10) so the wrapper stays thin. Concrete form of the "MCP server"
  bullet below.
- **Thin second compound, added purely as data** — proves the generic model. Highest-value
  demo stretch; the acceptance test already guarantees no engine edits are needed.
- **3D viewer** (`stmol` / `py3Dmol`) in the Streamlit UI.
- **Agentic search-to-approve** into the Reference tab (design the approval gate honestly).
- **MCP server** exposing the core to external agents (architected for; not built this week).
- **Model-adapter wired to a second model** — the local-model handoff
  (`docs/local-model-handoff.md`) is this, running on a separate machine.

## Longer-term ambitions (NOT this week, NOT requirements)

- **Publication-grade use.** Chansu may eventually be pushed toward publication-grade scientific
  use. Do not change scope or add requirements for this now — but when making architectural
  calls, prefer the option that preserves **reproducibility and auditability** (which the trust
  boundary + provenance tags already do).

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

## From the Codex core review (deferred; cheap correctness fixes already applied)

Real findings whose *timing* is Day 3+ or a deliberate design call — not fixed now, tracked here.

- **Adapter tool-result turn + typed messages (Day 3, before the Claude adapter).** `Message` is
  `(role, str)` and can't represent an assistant tool call, a tool result, or a `tool_call_id`.
  Redesign to a typed content/message model (user text; assistant text + tool calls; tool result
  with `tool_call_id`, name, content, error flag) before wiring a real backend. Add a two-turn
  tool-conformance test (request → result → final text); the handoff §6 tool smoke test should
  actually send a result back.
- **Typed streaming events (Day 3).** Replace `stream() -> Iterator[str]` with typed events
  (`TextDelta` / `ToolCallDelta` / `Completed(ReasoningResponse)`) so tool calls / stop_reason /
  usage are recoverable. v1 docstring now honestly says text-only.
- **Importance region as a set of atoms (Day 3–4).** An `ImportanceRegion` SMARTS may span many
  atoms, but the gate compares one resolved atom to one `modified_atom_idx`. Resolve a region to
  its full atom set, have generation report all changed parent atoms, and gate on set overlap.
- **Attachment-type compatibility enforcement (Day 2/3, in the matching layer).** Positions and
  transformations both declare attachment types, but `generate_at_position` doesn't compare them.
  Decide semantics (nonempty intersection? empty = wildcard?) and enforce with a flagged
  describe-only result on mismatch.
- **Fuller attribution / change-set (Day 2/3, with transformation hardening).** No-op products are
  now rejected; still want to confirm the declared reacting site actually participated (not just
  "product differs from parent"), and require attribution on the untargeted path.
- **Reaction cardinality is a hidden assumption (P2).** Engine supplies one reactant and takes
  `product_set[0]`. Formally constrain transformation data to one reactant / one desired product,
  add a `maxProducts` guard, or add data-driven product selection.
- **Contextual loader/model validation (P2).** Malformed JSON / wrong-typed fields surface as raw
  `KeyError`/`TypeError`; `Analog` can be built in contradictory states. Add a validation boundary
  with typed errors, distinguishing invalid input from "valid template, no clean candidate."
- **Wheel omits `data/` (deferred — we run from the repo).** `pip install`'d wheel has no
  `data/`, so the installed console script exits 2. Real only if we distribute a wheel (we don't
  this week). Fix later via `importlib.resources` *or* keep data external by design and document
  it — note the tension with the deliberate engine/data separation (`data/` at repo root).

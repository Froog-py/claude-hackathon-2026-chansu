# Chansu — build log

Terse per-day record of what shipped and the load-bearing decisions. The git history is the
full record; this is the map. (Also feeds the submission's "how we built it" narrative.)

## Naming
Project + Python package **Chansu** (chán sū / 蟾酥 — the traditional preparation the flagship
compound derives from). Branding only; the engine stays compound-agnostic (enforced by test).
Repo: `github.com/Froog-py/claude-hackathon-2026-chansu` (public). Local folder renamed to match.

## Day 1 — foundation + the two spikes (shipped)
- Generic data-model spine (`chansu/core/models.py`); no compound knowledge in `chansu/` (test-enforced,
  name + AST scan). Bufalin loaded from PubChem CID 9547215 as data only.
- Deterministic property module (MW/clogP/TPSA/HBD/HBA/RotB/Lipinski/Veber/Tanimoto/SA), all `[computed]`.
- Generation spike: encoded O-acetylation → valid, sanitized, stereo-preserved C3-acetate.
- Model-adapter interface skeleton + local-model handoff spec (`docs/local-model-handoff.md`).
- Adversarial self-verification (workflow) → fixed real bugs (false `[literature — cited]` tag,
  `ReactionFromSmarts` raising, weak acceptance test).

## Day 2 — precedent-backed strategy library (shipped)
- 6 compound-agnostic strategies keyed on liability class + attachment type, each with an
  **NCBI-verified** precedent citation (soft-drug/fluticasone, glycosylation/Katz2010,
  tumor-activated enzyme/capecitabine, hypoxia/TH-302, targeting-ligand/vintafolide, ester-prodrug/oseltamivir).
- Loader **refuses an uncited strategy**. Verification caught 3 author/year mislabels in the
  Claude Science draft → encoded NCBI-authoritative versions instead.
- Transformations linked per strategy; tractable ones generate, complex ones describe-and-highlight.

## Day 3 — literature grounding + reasoning layer (shipped)
- Research IP (research log + unpublished Bufalone draft) **gitignored** — public repo.
- Bufalin grounded: importance map (C14-OH high, C17 lactone warhead high, C3-OH medium),
  3 targets, 4 liabilities — every claim NCBI-verified.
- Deterministic matching engine: liabilities → strategies by class + attachment type; **honest
  failure** where none apply. Grounded, provenance-tagged report wired into the CLI.
- `ClaudeReasoningModel` (Opus 4.8) behind the adapter interface — mock-tested, reads the key
  from env at runtime (never touched), ready to run live.

## Day 4 — full loop + design memo (shipped; MUST-SHIP)
- Design pipeline: match → generate across actionable positions → **two-way gate** (edits on the
  high-importance C14/lactone flag, overridable) → **transparent Option-A scoring** (weighted sum
  of similarity/ease/druglikeness, weights shown) → ranked, provenance-tagged design memo.
- `python -m chansu.cli` → the complete tagged memo. 25 tests green.

## Day 4 review — Codex second pass (fixed)
Triaged all 12 findings against the actual code; fixed 11 with regression tests (25 → 35 tests),
deferred 1 with an honest in-code marker. Key trust-boundary fixes:
- **Two-way gate now round-trips:** `design` (orchestrate) split from `render_memo(…, result)` —
  a chemist's flag override + recorded reason survives into the memo (was silently discarded).
- **Describe-and-highlight made honest:** one described candidate *per* actionable position (was
  collapsed to one positionless one), each run through the same importance gate, and the memo now
  renders position + description + every flag (an essential-site described edit is now flagged).
- **Provenance enforced structurally:** `[literature — cited]` is emitted only with a real source;
  gate flags carry the region's citation; the author's validation note is labeled data-provided,
  not pipeline-verified.
- **Transparent score reproduces:** total computed from the rounded components shown; weights
  validated (exact keys, finite, in [0,1], sum 1).
- **Bounded honest failure:** "no strategy in the current curated library" — no invented
  formulation route (also a §5 generic-engine leak removed, with the hard-coded "complex
  conjugation" reason and the fake strategy-as-transformation id).
- **Adapter hardened:** malformed response / decode error → `ReasoningError`, timeout →
  `ReasoningTimeout`, `max_tokens` resolution fixed; tool support honestly marked receive-only.
- **Loaders:** strategy↔transformation attachment consistency + unique liability `kind` enforced.
Deferred (honest, tracked in SOMEDAY): full Claude tool-call/tool-result loop (adapter is
receive-only; the Day-4 loop never calls Claude), generation-time position/transform check (SMARTS
self-limits), capability-aware adapter (Opus-only by design). Review file: `CODEX_DAY4_DESIGN_LOOP_REVIEW.md`.

## Current cursor (resume here)
- **Pending:** commit the Day-4 review fixes (awaiting Luke's OK) — 12 files, +494/-98, 35 tests green.
- **Next:** Day 5 — Streamlit multi-screen UI (RDKit rendering + substructure highlighting) and
  demo hardening across 2–3 liabilities; lock the validation narrative (reproduce the by-hand
  soft-drug design; the warhead-edit flag is the two-way-gate moment). Then Day 6 = submit.
- Publishing/pushing needs Luke's explicit OK (auto-mode blocks public surfaces without it).

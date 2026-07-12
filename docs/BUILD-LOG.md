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

## Current cursor (resume here)
- **Pending:** triage + fix the second Codex review — `CODEX_DAY4_DESIGN_LOOP_REVIEW.md` (on disk).
  Discipline: verify each finding against the actual code before changing anything; the review was
  scoped to matching/scoring/pipeline/adapter/memo, chemistry & citations out of scope.
- **Next:** Day 5 — Streamlit multi-screen UI (RDKit rendering + substructure highlighting) and
  demo hardening across 2–3 liabilities; lock the validation narrative (reproduce the by-hand
  soft-drug design; the warhead-edit flag is the two-way-gate moment). Then Day 6 = submit.
- Publishing/pushing needs Luke's explicit OK (auto-mode blocks public surfaces without it).

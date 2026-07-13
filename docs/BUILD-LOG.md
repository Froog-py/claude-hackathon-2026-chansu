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
receive-only), generation-time position/transform check (SMARTS self-limits), capability-aware
adapter (Opus-only by design). Review file: `CODEX_DAY4_DESIGN_LOOP_REVIEW.md`. Merged as PR #2.

## Claude wired into the reasoning loop (§4 step 5, §6, §10 layer 2)
Correcting a real gap Luke caught: the tool claimed "powered by Claude" but Claude was inert at
runtime — the loop was 100% deterministic. §10's stretch is multi-model *pluggability*, not Claude;
§4/§6 put Claude as the reasoning engine **this week**. Now wired at exactly two call sites, both
through the `ReasoningModel` interface (not baked into the pipeline), everything else deterministic:
- **Strategy-match rationale** — per actionable (liability, strategy), Claude explains *why* the
  precedent-backed strategy applies, by analogy from the cited precedent + the importance map.
- **Memo narrative** — Claude writes the synthesis over the deterministic result.
- New layer-2 orchestrator `chansu/reasoning/design_reasoning.py` (`reason_over_design`); core
  `design()` stays model-free (layer 1 pure). `render_memo(…, reasoning=None)` renders it when
  present, deterministic-only when absent. CLI composes design → reason → render.
- **New provenance tag** `[reasoning — <model-name-from-adapter>]` (`Provenance.REASONING` +
  `reasoning_tag`): names the actual adapter model (no hardcoded "Claude"; swap → `[reasoning —
  qwen2.5]`), structurally enforced like `[literature — cited]` (no model → raises), and carries no
  citation claim of its own (the precedent keeps its separate `[literature — cited]`).
- Model-agnostic: swapping backends is an adapter/config change, not a pipeline edit. Only Claude
  (Opus) is implemented this week — no second backend built (deferred multi-model stretch).
- Degrades honestly: no key/SDK → first call fails → `available=False` → deterministic memo + note.
- 8 hermetic tests (mock clients, no live call): interface reach, grounded prompts, model-named tag,
  refusal-not-laundered, backend-down degradation, render with/without reasoning. **43 tests green.**
- **Live run** (real Claude prose): `uv pip install -e '.[claude]'` + `ANTHROPIC_API_KEY`, then
  `python -m chansu.cli`. This box has neither, so wiring is verified with mocks + a documented live
  path — not a live call.
- **Live smoke test (Luke ran it) — two fixes.** First live run produced no rationales/synthesis:
  the trust-boundary logic correctly refused unusable text, but the reasoning calls ran at
  `max_tokens=4096` and adaptive thinking + `effort=high` exhausted the budget before the visible
  answer (`stop_reason=max_tokens`). Fixes: reasoning requests now ask for **16000** max_tokens
  (`_REASONING_MAX_TOKENS`), and the CLI runs the reasoning model at **`effort="medium"`** (short
  analogical outputs, not deep reasoning). Second run still empty at 16000 → added **self-diagnosis**:
  a 200 with unusable text now records `stop_reason`/`output_tokens`/`text_len` into the memo's
  synthesis section, so the next run either works (medium effort fits) or prints the exact cause
  (max_tokens vs refusal vs empty end_turn). Verified via mocks (44 tests); awaiting Luke's next live run.

## 2026-07-12 — overnight loop: the empty synthesis is a safety refusal, not a code bug
Ran Luke's Ralph-style loop manually (the `ralph-loop` plugin wasn't actually loaded — "Unknown skill").
The self-diagnosing instrumentation added earlier paid off on the first live call:
- **Iteration 1** (`python -m chansu.cli`, live): auth works from the tool shell, and the diagnostic
  printed the real cause — `stop_reason=refusal, output_tokens=3, text_len=0` on **every** call. The
  earlier max_tokens/effort hypothesis was wrong; refusal is max_tokens-independent, which is exactly
  why the 4096→16000 change produced byte-identical output. Opus 4.8's safety classifier is declining
  these prompts — a known life-sciences false-positive per the Claude API reference (modifying a
  toad-venom toxin, with oncology "cytotoxic payload / warhead / release the toxin" strategy language).
- **Iteration 2**: added explicit, honest legitimate-therapeutic-research framing to `_SYSTEM` (per the
  loop's refusal rule) — still `stop_reason=refusal`. Kept the framing (accurate, weakens no
  trust-boundary rule); it simply didn't move the classifier.
- **Stopped here, deliberately.** One honest framing attempt is what the rule prescribes; rewording
  further to get *past* a safety refusal is circumvention (forbidden by the rule and by principle). A
  classifier refusal is a model-behavior constraint (rule-3c-like), not a fixable code bug.

**This is honest failure working as designed, not a broken feature.** The deterministic memo (grounding,
cited strategies, gated + scored analogs, honest failure) renders in full; the reasoning layer degrades
gracefully with an honest diagnostic when the model declines. That is on-thesis for a trust-boundary tool.

Kept: `max_tokens=16000` + `effort="medium"` (defensible defaults, not the fix), the honest `_SYSTEM`
framing, and the diagnostic instrumentation. 44 tests green. Nothing committed. No git operations run.

## 2026-07-12 — reasoning depth modes built; live finding: bufalin refuses even at strategy level
Built per `docs/reasoning-depth-design.md`: **Mode A** (strategy-level, compound-agnostic, default) +
**Mode B** (compound-specific, opt-in), with **B → A → deterministic-floor** graceful fallback, all through
the `ReasoningModel` interface. `reason_over_design(…, depth=)`; CLI `--depth strategy|compound`; the memo
surfaces `Reasoning mode:` + honest notes. **46 tests green** (incl. the B→A fallback + compound-agnostic default).

Live validation with bufalin (`--depth compound`, real Opus 4.8 calls):
- B (compound-specific) refuses uniformly, `category=bio` (expected); the B→A fallback runs smoothly and the
  memo stays complete (deterministic floor + honest notes).
- **Key finding:** Mode A (strategy-level, no compound name) cleared only **1 of 6** calls for bufalin — the
  bio classifier fires on most medicinal-chemistry-of-a-bioactive-compound prompts whether or not the compound
  is named. The one that cleared (`tumor_activated_prodrug_enzyme`, capecitabine precedent) produced genuinely
  good analogical reasoning, `[reasoning — claude-opus-4-8]`-tagged, respecting the no-prediction rule. So
  abstraction *helps a little* (1 vs 0) but is **not a reliable floor for a toxin like bufalin.** Even the
  benign soft-drug strategy refused at strategy level.
- **Reframe:** the **deterministic memo is the true reliable floor** (as built). Model reasoning is a
  best-effort enhancement that, for toxin-derived compounds, is sparse. For non-toxin compounds (the common
  case) both modes should clear far more often — untested until we add a clean compound.
- Do NOT retry-to-pass the classifier (that's gaming safety). Refusals are `category=bio`, deterministic-ish.

## 2026-07-12 — Sonnet 5 backend probe + reasoning-checks transparency panel shipped
**Step 1 — Sonnet 5 test (live, one-at-a-time probe, verbatim prompts, no retry-to-pass).** Pointed the
reasoning backend at `claude-sonnet-5` (effort=medium) and fired every Mode-A and Mode-B call for bufalin:
- **Mode A (strategy-level): 2 of 6 cleared** (Opus 4.8 was 1/6). Cleared: `targeting_ligand_conjugation`,
  `tumor_activated_prodrug_enzyme`. The rest `refusal`/`category=bio`.
- **Mode B (compound-specific): 0 of 6 cleared** (same as Opus).
- Notable: some Sonnet refusals carried *partial* text (~1000 chars) but `stop_reason=refusal` — the
  classifier fired mid-generation; `_usable_text` correctly rejects them (honest silence intact).
- **Verdict:** Sonnet 5 is *marginally* better (2 vs 1) but **not a reliable floor for a toxin** either.
  Per the decision rule (not reliable → positioning), we do **not** switch on reliability grounds. Sonnet 5
  remains a defensible default on other grounds (right tier for a shallow analogy, on-brand Claude, cheaper) —
  a low-stakes call for Luke since the deterministic memo is the true floor regardless.

**Step 2 — transparency/observability (shipped, 49 tests green).** Closed the observability gap and built
the reasoning-checks panel (Luke's directive: surface every check pass/fail/why; never dodge classifiers):
- `ReasoningResponse.stop_category` now captures the refusal `stop_details.category` (e.g. `bio`) first-class
  in the adapter (`chansu/reasoning/adapter.py`).
- `reason_over_design` records a `ReasoningCheck(label, passed, stop_reason, category, output_tokens)` for
  **every** call; `DesignReasoning.checks` + `.declined_checks()` expose them.
- `render_memo` renders a **Reasoning checks** panel: `"N of M calls passed; K declined by the model's own
  safety layer (bio)"` + a per-call pass/decline/why list, framed as the trust boundary working (not a bug).
- Live bufalin run confirms it end-to-end: `1 of 6 calls passed; 5 declined (bio)`, each call itemized.
- New tests: adapter category capture; every-call-recorded-with-why; memo surfaces declined (not just cleared).
- The `checks` list is the exact data the Day-5 Streamlit reasoning-checks panel will render.
- Nothing committed. No git ops. Scratchpad probe: `sonnet5_probe.py`.

## 2026-07-12 — Day 5 Streamlit UI BUILT + verified in-browser (function-first; styling next)
Built the full 3-tab app per `docs/day5-streamlit-ui-design.md`, foundation-first with an adversarial review
gate. **All features verified live in the browser. 61 tests green. Uncommitted.**

**Foundation (generic, framework-agnostic, no Streamlit/py3Dmol imports — verified):**
`region_match_atoms` (core/generation.py), `render_mol.py` (`draw_molecule_svg`, `molblock_3d`),
`references.py` (`Reference`, `build_reference_index`). +10 unit tests (`test_render_mol.py`,
`test_references.py`).

**Adversarial review workflow** (5 lenses → verify): 4 confirmed / 6 rejected. Applied all 4:
- references: aggregate `Citation.notes` across ALL citing claims (was first-only — dropped Katz 2010's
  glycosylation note); dedupe by *any shared identifier* (PMID or DOI), back-filling ids — robust for the
  future Claude-Science connector's heterogeneous citations.
- render test: assert `GetNumConformers` unchanged (the real no-mutation invariant, not just atom count).
- All locked with new tests.

**App (`chansu/ui/`):** `app.py` (sidebar: logo, compound selector, depth radio, About `@st.dialog` w/
GitHub+LinkedIn; 3 tabs) · `state.py` (cached deterministic design; reasoning gated behind a button in
session_state) · `workspace.py` · `viewer.py` · `gate.py` · `memo.py` · `sources.py`. Run:
`.venv/bin/streamlit run chansu/ui/app.py`. `.claude/launch.json` added.

**Verified in-browser (screenshots taken):**
- **2D viewer** — bufalin highlights correct: α-pyranone + C14-OH **red (high)**, C3-OH **amber (medium)**.
- **3D viewer** — py3Dmol ball & stick renders (CPK colors + importance recolor), rotate/zoom/pan native
  (the "rotate/zoom" ask = the 3D viewer). Drives 3Dmol.js from a CDN (3D needs internet; 2D is offline).
- **Two-way gate live seam** — C3 → green "no conflict"; C14 → ⚠ flag with the cited Na⁺/K⁺-ATPase reason +
  PMID/DOI → override recorded ("Overridden by chemist. Reason recorded: …"). Non-negotiable #4 as an ACT,
  reusing `resolve_position`/`importance_gate_flags`/`Flag.override` — zero engine change, zero duplication.
- **Reasoning-checks panel (live)** — "1 of 6 passed; 5 declined by the model's own safety layer (bio)",
  every call itemized green/red. The trust-boundary showcase, on demand.
- **Sources** — 12 deduped papers, group/sort, PubMed+DOI links, expandable "backs".
- **§5 live** — Ursolic Acid renders on its very different pentacyclic scaffold with correct highlighting
  (C28-COOH + C3-OH amber, C12=C13 core red). Second compound works end-to-end in the UI, data-only.

**Note (browser-automation only, NOT an app bug):** Streamlit's custom selectbox is hard to commit via
automated clicks; verified compound/representation switches by temporarily defaulting to them + restart
(all temp changes reverted; `grep TEMP-VERIFY` clean). A human user's clicks work normally.

**Next:** design/styling pass (Luke wants dark theme + custom CSS; `frontend-design` skill) — additive, no
logic change. Then Day 6 submit. Deferred niceties still open: per-analog 2D drawings in the memo; optional
2D pan-zoom; bundling 3Dmol.js for offline 3D.

## 2026-07-12 — §5 acceptance test with a real 2nd compound (ursolic acid) + Day-5 UI spec
**Day-5 UI design brainstormed + spec written** (`docs/day5-streamlit-ui-design.md`, uncommitted): focused
3-tab Streamlit app (Workspace + MolView-style 2D/3D viewer · Design memo + reasoning-checks panel ·
Zotero-style Sources), deterministic-floor-cached / reasoning-gated-behind-a-button, generic tested helpers
(`region_match_atoms`, `draw_molecule_svg`, `molblock_3d`, `build_reference_index`) with no chemistry in UI,
a **live two-way-gate seam** (Advisor diagnostic — the gate is cleanly standalone, so it's honest to build),
About modal, logo. Not built yet (awaiting Luke's "go").

**§5 acceptance test — ursolic acid (Claude Science compound, pentacyclic triterpenoid, CID 64945).** Ran a
structurally very different, benign compound through the FULL deterministic pipeline as **data only, zero
engine edits**. Result: **PASSES.** Loads, canonicalizes, all 5 locators (2 positions + 3 importance regions)
resolve uniquely on the new scaffold (no ambiguity), grounding + honest failure + scoring + provenance-tagged
memo all render. **No bufalin assumption leaked — the engine is genuinely general.**
- **One real finding (data, NOT engine):** attachment-type vocabulary drift. `ursolic.c28_cooh` declared
  `"carboxylic_acid"`; the strategy library + transformation use `"carboxyl"`. The matcher intersects those
  strings (correct generic behavior), so the ester-prodrug path silently degraded to describe-only and the
  memo printed a **misleading "no matching attachment point"** for a compound that *has* a carboxylic acid.
  Root cause: the Claude-Science-authored compound didn't use the library's controlled vocabulary.
- **Fix = one line of DATA** (`["carboxylic_acid"]` → `["carboxyl"]`), no engine change. Re-ran → the path is
  now actionable: `carboxyl_to_ethyl_ester` fires at C28 → a **valid, RDKit-sanitized, scored (0.781) ethyl-
  ester analog** for both `poor_solubility` and `poor_oral_bioavailability`; C3-OH + core intact. 49 green.
- **Correct honest failures kept:** `rapid_metabolism_cyp3a4` and `promiscuous_targets_selectivity` match no
  strategy class → the tool declines to over-claim (§6). Left as-is; not forced (ursolic's promiscuity ≠
  bufalin's isoform `poor_selectivity`).
- **Design note for the MCP connector (post-Day-5, NOT built):** `attachment_types` + `liability_classes`
  are an *undocumented controlled-vocabulary contract* shared between compounds and the library. Recommend
  (a) documenting the vocabulary Claude Science must emit, and optionally (b) a generic load-time LINT that
  *warns* (never errors, no compound knowledge) when a compound's handles/liabilities intersect no strategy,
  so silent degradation ("handle matches nothing in the current library") becomes visible.
- **Reasoning path for ursolic (benign) untested** — Mode A/B may clear far more than for bufalin; worth a
  quick live probe during Day 5 (bonus, not §5).

## Current cursor (resume here) — for Luke
- **DONE this session:** Sonnet 5 probe (2/6 A, 0/6 B — not reliable, don't switch on reliability grounds);
  reasoning-checks transparency panel + `bio`-category capture shipped and tested; Day-5 UI spec written;
  **§5 acceptance test passed** with ursolic acid (data-only vocab fix; valid generated analog). 49 green, uncommitted.
- **Ursolic acid is demo-ready as the 2nd compound** — proves §5 (generality) on a very different scaffold and
  now exercises the actionable-generation path bufalin never did (it has no carboxyl); it'll appear in the
  Day-5 compound selector automatically.
- **Open decision for Luke:** default reasoning backend — keep `claude-opus-4-8` or switch to `claude-sonnet-5`?
  Recommend Sonnet 5 (on-tier, on-brand, cheaper, marginally better) but it barely matters. One-line change in
  `chansu/cli.py:58` (`ClaudeReasoningModel(model="claude-sonnet-5", effort="medium")`). NOT changed yet.
- **Next:** on Luke's "go" — build Day 5 per `docs/day5-streamlit-ui-design.md` (helpers+tests → 2D viewer →
  tabs → references → staged: 3D, gate seam, About). Then Day 6 = submit.
- **Open decision for Luke:** default reasoning backend — keep `claude-opus-4-8` or switch to `claude-sonnet-5`?
  Recommend Sonnet 5 (on-tier, on-brand, cheaper, marginally better) but it barely matters. One-line change in
  `chansu/cli.py:58` (`ClaudeReasoningModel(model="claude-sonnet-5", effort="medium")`). NOT changed yet.
- **Blocked:** clean second compound (validates Mode A/B for non-toxins) — needs Luke's Claude Science data.
- **Next:** Day 5 — Streamlit multi-screen UI (RDKit rendering + substructure highlighting; render the
  reasoning-checks panel from `DesignReasoning.checks`). Then Day 6 = submit.
- **Strategic call (design, not code):** given Mode A is unreliable for toxins, how should the reasoning
  layer be positioned? Options, most-on-thesis first:
  1. **Accept graceful degradation** (recommended) — ship the deterministic memo as the core deliverable;
     the Claude rationale/synthesis is a value-add that honestly degrades + self-diagnoses when declined.
     Most consistent with §6 (honest failure is a feature); arguably a demo highlight.
  2. Route the *literature reasoning* through **Claude Science** (already the planned §9 component) rather
     than a raw Messages-API call — a different surface that may handle cited-literature synthesis better.
  3. Human-in-the-loop: Luke evaluates whether a different backend/endpoint fits. Do NOT reword prompts to
     evade the classifier.
- **Do NOT** treat this as a bug to keep hacking. The wiring is correct and fully mock-tested; the block is
  a safety-layer judgment that belongs to Luke, not to an autonomous loop.
- Claude-reasoning-loop work is uncommitted on `feature/claude-reasoning-loop`, awaiting Luke's OK.
- Then: Day 5 — Streamlit UI + demo hardening; Day 6 — submit.
- **Next:** Day 5 — Streamlit multi-screen UI (RDKit rendering + substructure highlighting) and
  demo hardening across 2–3 liabilities; lock the validation narrative (reproduce the by-hand
  soft-drug design; the warhead-edit flag is the two-way-gate moment). Then Day 6 = submit.
- Publishing/pushing needs Luke's explicit OK (auto-mode blocks public surfaces without it).

# Design — reasoning depth modes (strategy-level floor + compound-specific opt-in)

**Date:** 2026-07-12 · **Status:** approved (brainstormed with Luke), implementing · **Not committed** (Luke commits).

## Problem
The reasoning layer sent compound-specific prompts (compound name + toxin / importance-map detail) to
the model. For sensitive compounds — bufalin is a toad-venom toxin, and the oncology strategy language
is "cytotoxic payload / warhead / release the toxin" — the safety classifier **refuses**
(`stop_reason=refusal`, `stop_details.category=bio`, HTTP 200, `output_tokens≈1–3`, no thinking). Confirmed
on Opus 4.8; Luke's other local model refuses too, so this is about the **request shape**, not one vendor.
Rewording to dodge is brittle and transient (models change; Anthropic may relax bio policy; other models
plug in). We need a **model-agnostic** solution that keeps performance and sacrifices nothing on our side.

## Decision — two reasoning depths over the same adapter interface
Selected by a `depth` parameter on the reasoning orchestration:

- **Mode A — strategy-level (default, the enhancement "floor").** The model reasons at the
  strategy ↔ liability-class ↔ attachment-type ↔ precedent level, **compound-agnostic**. Prompts carry
  NO compound identity and NO importance-map specifics — only the strategy (concept / mechanism /
  precedent / citation), the liability *class*, and the attachment *type(s)*. This is where the reasoning
  naturally lives — the strategy library keys on class + type (PROJECT.md §7, "the moat") — so it is not a
  dodge, it is the correct altitude. Benign textbook med-chem → should clear safety classifiers.
  Compound-agnostic → **cacheable / reusable** across every compound with that liability+strategy (efficiency).
- **Mode B — compound-specific (opt-in).** The current prompts (full compound context). Richer per-compound
  rationale, but trips classifiers on sensitive compounds.

## Fallback — graceful, per item
The **deterministic memo** (grounding, cited strategies, positions, scores, gate flags) is the *true*
always-there floor — no model required. Model reasoning is a best-effort layer on top:

- `depth="compound"` (B): try B → on refusal/unusable, fall back to Mode A for that item → if A is also
  unusable, no rationale for that item + an honest note. (B → A → deterministic floor.)
- `depth="strategy"` (A): try A → on refusal/unusable, no rationale + an honest note. (A → deterministic floor.)

Each tier degrades gracefully with the existing self-diagnostic (`stop_reason` + usage). Never a dead end;
never worse than the deterministic memo. **Mode A is not 100% guaranteed** — a few strategy concepts are
themselves about cytotoxic delivery and may still trip; verify empirically for the flagship's strategies.

## Scope this week
- Build **Mode A** prompt builders as the default/floor. Keep **Mode B** (= current prompts) behind the
  `depth` flag. Wire the **B → A → floor** fallback. Mock-based deterministic tests proving each tier
  (a mock that refuses when the compound name is in the prompt but passes at strategy level — simulating the
  real `bio` classifier).
- Default depth = `strategy` (safe) — the **bufalin demo runs on A**.
- CLI: a `--depth compound` option to select B, so we can prove the **B→A drop on bufalin** (the critical
  tripped path). UI toggle is Day 5 *if time*.
- Second (clean) compound to actually *demo* B succeeding comes later via Claude Science (pure data — §5).

## Model-agnostic + trust boundary
The depth choice and fallback live at the reasoning-orchestration seam; any backend plugs in via
`ReasoningModel`. When a model relaxes policy (or a research-tuned model is used), Mode B just succeeds more
often — no pipeline change. Mode A *strengthens* the trust boundary: the model explains documented
principles, the deterministic engine does all compound-specific mapping (positions/importance/scores) — less
hallucination surface, more auditable. Reasoning stays `[reasoning — <model>]`-tagged; the depth
(strategy vs compound) is surfaced so the reader knows which they're seeing.

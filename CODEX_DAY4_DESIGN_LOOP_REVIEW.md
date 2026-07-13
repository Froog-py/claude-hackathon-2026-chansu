# Day-4 engine and full design-loop review — Codex handoff

Review target: `d54e79c41c7adfcbac3c1c1f729e57a585b506fd` (`main` / `origin/main`)  
Scope: matching, scoring, pipeline composition, `render_memo`, and the Claude adapter  
Excluded: chemistry correctness and citation validity  
Disposition: review only; no engine code was changed

## Executive assessment

The valid-structure happy path is coherent: matching is deterministic, actionable encoded
transformations generate once per matching position, generation attaches gate flags, valid products
are scored, and `render_memo` ranks valid candidates per liability by descending score. The current
flagship produces two valid candidates, flags the high-importance one, and reports the liability
with no matching strategy.

The complete design loop does **not** yet satisfy the two-way-gate or provenance contracts. The
highest-impact problems are:

1. `render_memo` recomputes the design, so a user's gate override and recorded reason are discarded.
2. Describe-only strategies collapse multiple actionable positions into one positionless candidate,
   skip position-specific gating, and then lose all fallback flags in the memo.
3. The renderer can print `[literature — cited] (uncited)`, and it emits untagged free-form claims
   from `validation_note` and untagged literature-derived gate messages.
4. The Claude adapter can initiate and parse a tool call but cannot represent the assistant/tool-
   result turns needed to finish the tool loop.
5. Malformed Claude responses can become successful `end_turn` responses, while response-decoding
   and timeout failures do not satisfy the adapter's documented error taxonomy.
6. The first printed score equation does not equal the displayed weighted terms, and custom weights
   are unvalidated despite the claimed `[0, 1]` bound.

I would fix those before treating the Day-4 memo as the must-ship trust-boundary deliverable.

## Findings

### P1 — Gate overrides cannot survive into `render_memo`

**Locations:** `chansu/report.py:121-142`, `chansu/report.py:145-146`,
`chansu/core/models.py:173-194`

The caller can run `design()`, locate a flag, and call `flag.override(reason)`. However,
`render_memo(compound, mol, library)` immediately calls `design()` again and creates fresh candidates
and flags. It has no parameter for an existing `DesignResult`. Even if an overridden candidate could
be passed in, `_candidate_lines()` always prints the generic “overridable” sentence and never prints
`overridden` or `override_reason`.

Reproduction at HEAD:

```text
override_in_result = reviewed and accepted
override_in_memo   = False
```

This breaks the required “override with reason recorded” half of the two-way gate at the final
output boundary.

**Recommended fix:** separate orchestration from rendering. Make the primary renderer accept a
`DesignResult` that the UI/user has reviewed, for example `render_memo(compound, mol, result)`. A
convenience `design_and_render(...)` wrapper can remain for the CLI. Render each flag's current state,
including its reason when overridden. Add a round-trip test: design -> override one flag -> render ->
assert the reason appears and a different candidate remains unoverridden.

### P1 — Describe-only paths discard actionable positions and bypass or hide the gate

**Locations:** `chansu/core/pipeline.py:28-36`, `chansu/core/pipeline.py:50-100`,
`chansu/report.py:121-142`, `chansu/report.py:180-195`

There are three related correctness failures:

1. When a strategy has no encoded transformation but has multiple actionable positions, the
   pipeline emits **one** describe candidate rather than one per position or one candidate carrying
   the full position set. On the flagship, several strategies match both `c3_oh` and `c14_oh`, but
   each becomes one candidate with `modified_atom_idx=None` and “the specified position.”
2. Because `_describe_candidate()` never calls the position-specific gate, a described proposal at
   a high-importance actionable position receives no high-importance flag.
3. When an encoded transformation fails at a known position, generation correctly returns a
   describe-only analog containing the atom index, position-specific description, `describe_only`
   flag, and possibly `high_importance_region` flag. The memo ignores `analog.description` and all
   flags for described candidates, printing only the strategy concept and error.

A malformed-transformation probe produced two fallbacks at atoms 5 and 27; atom 27 carried both
`describe_only` and `high_importance_region`. The memo printed two indistinguishable describe entries,
neither position label, and no flags.

Valid candidates also do not retain/render a position ID or label, so the two same-strategy entries
in the current memo cannot be directly traced back to C3 versus C14 without interpreting the
structure or flag.

**Recommended fix:** make position identity part of `Candidate` (ID, label, and resolved atom), not
an incidental generation detail. For an actionable strategy without a transformation, emit one
position-specific described candidate per position and run the same importance gate. Render the
position, `analog.description`, and every flag for both valid and described candidates. If the
product is intentionally position-agnostic, model that explicitly as a set of candidate positions
rather than pretending there is one unspecified site.

### P1 — The memo's provenance claim is not enforced

**Locations:** `chansu/report.py:22-33`, `chansu/report.py:49-70`,
`chansu/report.py:121-141`, `chansu/report.py:197-206`, `chansu/core/models.py:73-104`

The current flagship's targets, liabilities, importance regions, and strategies all have citation
sources, so those particular `[literature — cited]` lines are populated. The generic renderer is
still dishonest for valid model states:

- `Target`, `Liability`, and `ImportanceRegion` allow `citation=None`, but their renderers always add
  `_LIT`. A programmatic uncited compound prints `[literature — cited] (uncited)` for its target,
  liability, and liability header.
- `_cite()` returns `None` when a `Citation` object exists but has no `source`, so the memo can print
  `[literature — cited] None`. Strategy loading requires a label but not a source.
- Candidate gate messages repeat the literature-derived importance reason without a provenance tag
  or the importance region's citation.
- `compound.annotations['validation_note']` is emitted as arbitrary, untagged prose immediately after
  the memo claims every output claim is tagged.

The current validation note also demonstrates why blind free-form rendering is unsafe: it says the
tool independently flags editing the C17 region, but the actual `DesignResult` contains candidates
only for C3 and C14 and the emitted high-importance flag is for C14. That is a control-flow/data
consistency issue, not a chemistry judgment. Nothing verifies the narrative against the result.

The normal candidate sections otherwise avoid claiming that an analog solves a liability: analogs
and described concepts are tagged as hypotheses, deterministic values are computed, and the memo
restates that efficacy is not predicted. The unstructured validation note and untagged flags are the
exceptions.

**Recommended fix:** make renderable scientific claims carry provenance and a citation structurally.
Do not select `_LIT` independently of citation presence. Either reject uncited literature claims at
the data boundary or render them as explicitly uncited/unverified without the cited tag. Replace
`validation_note: str` with structured, provenance-bearing claims, or label it clearly as user-
provided narrative and never present it as pipeline-verified. Gate flags should retain the matched
region ID/citation and render both the deterministic overlap and cited importance claim.

### P1 — The Claude adapter cannot complete a tool-call conversation

**Locations:** `chansu/reasoning/adapter.py:20-49`, `chansu/reasoning/adapter.py:155-190`

Initial tool mapping is correct: tool specs are sent in Anthropic's schema, and returned `tool_use`
blocks are mapped to `ToolCall`. The provider-neutral `Message` contract still contains only
`role: str` plus `content: str`. It cannot represent:

- the assistant response containing the original `tool_use` blocks;
- a user `tool_result` block;
- `tool_use_id` correlation;
- tool result errors or parallel results.

Consequently the adapter can ask for a tool but cannot send the result back and get a final answer.
Anthropic's official tool lifecycle requires the original assistant tool-use content followed by a
user message containing correlated tool-result blocks. See
[Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls).

**Recommended fix:** introduce typed message content shared by all adapters: text, assistant tool
call, and user tool result with call ID, content, and error state. Add a real conformance test covering
request -> two parallel calls -> results -> final text. Until that exists, remove or clearly mark
tool support as receive-only rather than claiming an implementable tool-capable contract.

### P1 — Claude response validation and error normalization can turn failures into apparent success

**Locations:** `chansu/reasoning/adapter.py:58-72`, `chansu/reasoning/adapter.py:174-208`

Confirmed behaviors:

- A response object with no `content`, `usage`, or `stop_reason` becomes
  `ReasoningResponse(text="", stop_reason="end_turn")`. A malformed response is silently promoted to
  successful completion.
- `_to_response()` runs outside the request `try` block. A malformed tool block such as
  `input=None` raises raw `TypeError`, not the required `ReasoningError`.
- Timeouts are caught by the broad exception handler and normalized to `ReasoningError`, never the
  defined `ReasoningTimeout`.
- A `refusal` response containing text returns that text even though the class docstring promises
  empty text. Preserving partial text can be reasonable, but the contract must mark it as partial/
  unusable rather than relying on every caller to notice a free-form stop reason.
- The `ReasoningResponse.stop_reason` comment lists only three values, while the current API also
  defines `stop_sequence`, `pause_turn`, `refusal`, and `model_context_window_exceeded`. Refusal
  details and the matched stop sequence are available only through provider-specific `raw`.

Official guidance distinguishes successful stop reasons from SDK exceptions, requires callers to
handle truncation/refusal/pause explicitly, and exposes a typed timeout error. See
[Stop reasons and fallback](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons)
and the [Python SDK error documentation](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python).

**Recommended fix:** validate response shape and supported block fields before constructing a
response; missing required fields should raise `ReasoningError`. Normalize response-decoding errors
too. Map the SDK's timeout exception to `ReasoningTimeout`, preserve retryable/status/request-ID
metadata, and use a closed stop-reason enum plus explicit completion/truncation/refusal semantics.
Expose `stop_details` and `stop_sequence` provider-neutrally if callers are expected to act on them.

### P2 — The printed score equality does not use the values being shown

**Locations:** `chansu/core/scoring.py:44-60`, `chansu/report.py:121-130`,
`tests/test_pipeline.py:44-56`

`score()` computes `total` from unrounded similarity/ease values, then separately rounds each stored
component. The memo prints the rounded components next to the total and uses an equals sign.

The first current candidate prints:

```text
score 0.776 = 0.5*0.742 + 0.25*0.622 + 0.25*1.0
```

The displayed right-hand side is `0.7765`, not `0.776`. This is small numerically but violates the
explicit transparency/reproducibility claim. The test allows an error of `0.02`, which is far too
large for a value shown to three decimal places.

Custom weights are also unvalidated. Passing weights of `1, 1, 1` produced a total of `2.364` even
though `ScoreBreakdown` documents total in `[0, 1]`; a missing key raises raw `KeyError`. Negative,
non-finite, or non-normalized weights can corrupt ranking.

**Recommended fix:** validate exact required keys, finite nonnegative values, and a sum of one (or
normalize explicitly). Choose one rounding policy: compute total from the stored/displayed
components, or retain/render enough raw precision for the printed equation to reproduce the stored
total. Tighten the test to the actual display precision and test invalid weights, NaN, and ties.

### P2 — Matching checks strategy/position types but not transformation compatibility

**Locations:** `chansu/core/matching.py:37-58`, `chansu/core/pipeline.py:77-85`,
`chansu/core/models.py:107-140`

The matching rule itself correctly uses a nonempty intersection between
`Strategy.attachment_types` and `ModifiablePosition.attachment_types`, preserving all actionable
positions. It also correctly distinguishes “no strategy for this liability class” from “strategy
exists but no compatible position.”

The encoded `Transformation.applies_to_attachment_types` field is never checked. I changed the
loaded transformation's declared applicability to `['amine_only']`; because the strategy still said
`hydroxyl`, matching called it actionable and the pipeline emitted valid products at hydroxyl
positions.

**Recommended fix:** validate strategy/transform consistency when loading the library and enforce
position/transform compatibility before generation. A data inconsistency should be a contextual
library validation error or a flagged describe-only candidate, not a silently generated analog.
Define empty-list semantics explicitly.

### P2 — Honest failure overstates what was searched and invents a formulation route

**Locations:** `chansu/core/matching.py:42-59`, `chansu/report.py:73-102`,
`chansu/report.py:170-179`

`match_strategies()` honestly returns `strategy=None` when the supplied library contains no strategy
for a liability. The memo upgrades that bounded fact to “no well-precedented strategy applies,” which
sounds universal. The engine only knows that none in the **current supplied library** matched.

It then appends “may route to formulation-delivery” for every unmatched liability. A synthetic
`insufficient_potency` liability received the same route, even though no route was declared in data.
With a partial library, all omitted strategy classes receive this statement as well.

This is both a trust-boundary overclaim and a generic-engine leak.

**Recommended fix:** say “no strategy in the current curated library matches this liability.” Include
library identity/version if available. Put any out-of-scope route on the liability or matching policy
as data, and render it only when explicitly declared.

### P2 — The generic engine contains a strategy-specific fallback explanation and false transform metadata

**Locations:** `chansu/core/pipeline.py:50-67`, `chansu/core/pipeline.py:87-99`

Every actionable strategy without `transformation_id` gets the hard-coded reason:

```text
no encoded transformation for this strategy yet (complex conjugation)
```

That is not generic. A programmatic unsupported strategy unrelated to conjugation received the same
reason. The description should come from strategy data or use the generic portion only.

`_StrategyAsTransformation` also passes `strategy.id` into `_describe_fallback()`, causing
`Analog.transformation_id` to contain a strategy ID even though no transformation exists. That is
incorrect audit metadata hidden by the current text renderer.

No named flagship compound or target is hard-coded into the new Python modules, and the existing
blacklist test passes. These semantic assumptions show why the generic-engine rule cannot be proven
by forbidden-token scanning alone.

**Recommended fix:** create a first-class described-design type or allow
`Analog.transformation_id=None`; do not adapt a strategy into a fake transformation. Store a generic
fallback reason or data-authored generation note on the strategy.

### P2 — A missing transformation aborts the entire design loop mid-run

**Locations:** `chansu/core/pipeline.py:69-101`, `chansu/core/loaders.py:133-137`

If a strategy names a missing transformation file, `load_transformation()` raises
`FileNotFoundError` and no other liabilities/candidates reach the memo. Current tests verify that the
checked-in library's transformation IDs exist, so the flagship is safe, but the public design API
has no declared policy for bad/new data.

**Recommended fix:** choose one explicit boundary:

- validate the complete compound/strategy/transformation graph before design and fail once with a
  contextual data-integrity report; or
- turn a per-strategy load/parse failure into a flagged describe-only candidate and continue other
  liabilities.

Do not leave it as a raw mid-loop file exception. Also consider injecting a transformation resolver
or data directory: `design()` currently always loads from the default repository data even if the
compound/library were loaded through an override directory.

### P2 — The Claude request configuration is Opus-4.8-specific despite a configurable model

**Locations:** `chansu/reasoning/adapter.py:131-172`, `pyproject.toml:13-17`

For the default model, the request mapping is current and correct: Opus 4.8 accepts adaptive thinking
plus `output_config.effort`, and non-default sampling parameters should be omitted. See
[What's new in Claude Opus 4.8](https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-8)
and the [Messages API reference](https://platform.claude.com/docs/en/api/python/messages/create).

The constructor accepts any model string but always sends Opus-4.8-specific thinking/effort behavior
and always ignores `ReasoningRequest.temperature`. Either the adapter is specifically Opus 4.8 and
should enforce that, or it needs model-capability-aware mapping.

There is also a max-token contract bug: `request.max_tokens or self.default_max_tokens` means the
constructor default is unreachable during normal requests because `ReasoningRequest` already defaults
to 4096. Passing `0` selects the constructor default even though the API defines zero as a valid
request value. In a probe, a requested zero was sent as 777.

Finally, mock tests prove dictionary mapping but not that the declared `anthropic>=0.40` minimum
supports the newer request parameters. Pin the minimum SDK version actually exercised by CI and add
one SDK-shape test without a network call.

### P3 — Liability identity is reduced to `kind`, which can conflate repeated liabilities

**Locations:** `chansu/core/pipeline.py:28-47`, `chansu/report.py:166-186`

`Candidate.liability` is a string, candidates are grouped by that string, and unaddressed liabilities
are reduced to a set of kinds. If a compound contains two liability records with the same kind but
different details/citations, each rendered liability iteration receives the combined candidates for
both records. There is no loader validation requiring unique kinds.

**Recommended fix:** retain a liability ID/object on each candidate and group by stable identity, or
validate that `kind` is unique per compound and document it as the key.

## Requested edge-case results

| Case | Current result | Assessment |
|---|---|---|
| Liability with no strategy | Added to `DesignResult.unaddressed`; memo prints honest-failure branch | Control flow works, wording overclaims beyond the supplied library and invents formulation routing. |
| Strategy with multiple actionable positions + encoded transform | Generates/scored once per position | Correct generation count, but candidate/memo do not retain or display position identity. |
| Strategy with multiple actionable positions + no transform | Emits one positionless described candidate | Incorrect; positions collapse and position-specific gate is skipped. |
| Reaction describe-only fallback | Candidate retains known atom and flags | Pipeline state is useful, but memo discards position description and every flag. |
| Relevant strategy with no compatible attachment | Emits one described candidate and does not fabricate a site | Correct distinction; reason is honest. |
| Entirely unaddressed liability | Not scored or ranked | Correct, subject to bounded-library wording above. |
| Valid candidates | Scored after generation/gating; ranked descending per liability | Correct happy path. Flags deliberately do not alter score. |

## What should be preserved

- Liability-class matching and strategy/position attachment intersection are simple and deterministic.
- The matcher never invents a strategy object.
- Multiple actionable positions with an encoded transformation are all attempted.
- Valid products are sanitized before scoring, and describe-only candidates are not scored.
- Candidate ranking is descending by the transparent total and is performed independently per
  liability in the memo.
- Flags are surfaced beside valid candidate scores rather than being silently folded into ranking.
- The default Claude request uses the correct current Opus 4.8 thinking/effort shape, omits rejected
  sampling parameters, and correctly parses text/tool blocks and basic usage.
- Refusal is preserved as a stop reason rather than mislabeled `end_turn` when the field is present.
- The normal candidate prose consistently calls designs hypotheses and does not claim they solve the
  liability or predict efficacy.

## Verification performed

- `.venv/bin/python -m pytest -q` — **25 passed**.
- `.venv/bin/python -m chansu.cli` — rendered the complete current memo.
- Traced all current matches, candidates, scores, flags, and unaddressed liabilities.
- Confirmed per-position generation for the two encoded flagship candidates.
- Confirmed four actionable no-transform matches each collapse two positions into one candidate.
- Confirmed user override state is absent from a subsequent memo.
- Confirmed the first displayed score terms sum to `0.7765` while the memo prints `0.776`.
- Confirmed invalid custom weights can produce totals above one and missing keys raise `KeyError`.
- Confirmed `[literature — cited] (uncited)` on valid uncited model objects.
- Confirmed a strategy/transformation attachment mismatch can still generate valid candidates.
- Confirmed malformed adapter responses can become empty `end_turn`, response parsing can raise raw
  `TypeError`, timeouts map to the wrong exception class, and refusal text is retained contrary to
  the adapter docstring.
- Cross-checked Opus 4.8 request, tool-result, stop-reason, and SDK error semantics against current
  official Claude Platform documentation.

Environment: Python 3.12.13, RDKit 2026.03.3. The optional `anthropic` SDK is not installed in the
repository venv; adapter execution was tested with injected clients, as the suite does.

## Suggested implementation order

1. Split design execution from memo rendering so reviewed gate state is renderable and persistent.
2. Make position identity first-class and run/render the gate for every valid or described position.
3. Enforce provenance structurally and remove unchecked free-form claims from the verified memo.
4. Add typed tool-call/tool-result messages and strict Claude response/error handling.
5. Make score display exactly reproducible and validate weights.
6. Validate strategy/position/transformation compatibility as one data graph.
7. Bound honest-failure wording to the supplied library and make routing data-driven.
8. Remove strategy-specific fallback prose and fake transformation IDs from the engine.
9. Define missing-transformation/data-resolver behavior and liability identity.

## High-value tests to add

1. `design -> override -> render` preserves and prints the exact reason.
2. Two actionable positions yield two position-labeled described candidates and independent gate
   states when there is no encoded transformation.
3. A failed encoded transformation at a high-importance position renders the position and both
   fallback/high-importance flags.
4. Every rendered `_LIT` claim has a nonempty citation source; uncited inputs cannot receive the tag.
5. Validation narrative cannot claim a generated/flagged position absent from `DesignResult`.
6. The rendered score equation recomputes to the shown total at the shown precision; invalid weights
   are rejected.
7. Strategy/transform attachment mismatch is rejected before reaction application.
8. Honest failure says “none in current library” and never emits an undeclared route.
9. Claude tool request -> result -> final response, including parallel calls and tool errors.
10. Missing/malformed Claude fields, malformed tool input, timeout, refusal with text, truncation,
    pause-turn, and context-window stop paths.
11. Missing transformation follows the chosen validate-first or per-candidate fallback policy without
    a raw mid-loop exception.

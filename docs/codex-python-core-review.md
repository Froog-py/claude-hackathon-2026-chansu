# Python core review — Codex handoff

Review target: commit `4ad2dbe07a98512e067430839a6626e6017296bc` on `main`  
Scope: `chansu/` and `tests/`; chemistry correctness and citations intentionally excluded  
Disposition: review only. No production code was changed.

## Executive assessment

The core is compact, readable, and presently free of obvious named compound-specific branches.
The existing seven tests pass, malformed reaction SMARTS degrade to a describe-only result, both
configured positions are correctly attributed through RDKit's `react_atom_idx`, and returned
products are sanitized before being emitted.

The contracts are not yet strong enough to build the next layers on safely. The most important
problems are:

1. The model adapter cannot represent a complete tool-call round trip, and its streaming contract
   cannot return the final tool calls, stop reason, or usage it promises.
2. Position and importance locators silently select the first SMARTS match and are not validated.
   This is a real generic-engine leak: the engine currently assumes a compound has one
   unambiguous match for every declared site.
3. Gate flags are shared mutable objects across analogs, so overriding one candidate can override
   another candidate without user intent.
4. The describe-and-highlight fallback does not retain the known atom to highlight, and one early
   fallback loses the parent ID.
5. Sanitization proves that a product is parseable, but the engine does not prove that the encoded
   edit happened. A no-op reaction is accepted as a valid analog.
6. Declared attachment compatibility is ignored, and installed wheels omit all default data.

I would fix the high-priority contract issues before wiring a Claude adapter or building the UI.

## Findings

### P1 — The adapter cannot represent a tool-result turn

**Locations:** `chansu/reasoning/adapter.py:20-49`, `docs/local-model-handoff.md:73-79`

`Message` contains only `role` and string `content`, and the documented roles are only `user` and
`assistant`. There is no representation for:

- an assistant message containing one or more `ToolCall` objects;
- a tool-result message;
- the `tool_call_id` that correlates a result to its call;
- structured tool-result content or a tool error.

The handoff says that the core executes a tool and sends its result in the next turn, but that next
turn cannot be expressed by `ReasoningRequest`. An adapter can invent a provider-specific
JSON-in-text convention, but then adapters are no longer interchangeable.

**Recommended contract change:** use a typed content/message model. At minimum, support user text,
assistant text plus tool calls, and tool results carrying `tool_call_id`, `name`, content, and an
error flag. Define the provider-neutral ordering rules for multiple calls. Add a two-turn
conformance test: model requests a tool, caller returns its result, model produces final text.

### P1 — The streaming contract is internally impossible

**Locations:** `chansu/reasoning/adapter.py:75-97`

`stream()` returns only `Iterator[str]`, while its docstring says tool calls surface on a final
aggregated `complete`-style response. No such response is yielded or returned. A caller cannot
obtain tool calls, `stop_reason`, usage, or a partial/final distinction. Calling `complete()` after
streaming would make a second, potentially different model request.

**Recommended contract change:** either remove streaming from the v1 contract until needed, or
yield typed stream events (`TextDelta`, `ToolCallDelta`, `Completed(ReasoningResponse)`). A simple
backend may emit one text delta followed by one completed event. Test both a text-only stream and a
tool-call stream.

### P1 — Locator ambiguity and invalid locator data can select the wrong site or bypass the gate

**Locations:** `chansu/core/generation.py:34-45`, `chansu/core/generation.py:154-175`,
`chansu/core/loaders.py:51-54`, `chansu/core/loaders.py:64-83`

`resolve_position()` always uses `matches[0]`. `StructureLocator` has no match selector and no
uniqueness policy. On `OCCO`, for example, `[OX2H1]` matches both oxygens and the engine silently
returns atom 0. The choice depends on RDKit atom ordering rather than declared data intent.

Locator data is also not validated at load time. A negative `target_atom` such as `-99` causes an
uncaught `IndexError`. A malformed or nonmatching high-importance locator returns `None`, after
which `importance_gate_flags()` silently emits no flag. That violates the project's “never silently
allows” gate rule.

This is a direct weakness in the generic-engine claim. New compounds with repeated motifs cannot
reliably identify a desired site using the current data contract; a code or schema change will be
required.

**Recommended contract change:** make ambiguity explicit in data, for example with `match_index`,
an expected match count, or a locator that resolves to a set. At compound-load/validation time:

- parse every SMARTS;
- validate `target_atom` as a nonnegative in-range integer;
- require positions to resolve according to their declared match policy;
- treat an unresolved importance region as a data error or explicit gate flag, never as “not
  important.”

Use a typed `LocatorError` carrying the compound, locator, and reason.

### P1 — Importance “regions” are reduced to one atom, so edits can escape the gate

**Locations:** `chansu/core/models.py:50-59`, `chansu/core/models.py:73-85`,
`chansu/core/generation.py:154-175`

An `ImportanceRegion` has a SMARTS pattern that may span several atoms, but the gate resolves only
`locator.target_atom` and compares that single atom to a single `modified_atom_idx`. Editing another
atom or bond inside the matched region is not flagged. A multi-atom transformation also cannot
report all touched parent atoms.

**Recommended contract change:** distinguish a single attachment-site locator from a region
locator. Resolve a region to the complete set of parent atom indices in its selected match(es).
Have generation derive/report the set of changed parent atoms and bonds, then gate on set overlap.
If the engine cannot establish attribution, return a flagged describe-only result instead of a
quiet structural candidate.

### P1 — Gate overrides leak between candidates through shared `Flag` objects

**Locations:** `chansu/core/generation.py:191-197`, `chansu/core/models.py:170-188`

`gate_flags` is created once and the same mutable `Flag` instances are extended into every analog.
Calling `analog_a.flags[0].override(...)` mutates the flag visible on `analog_b`. I reproduced this
with two generated candidates: both became overridden and both received candidate A's reason.

This corrupts the two-way gate's audit meaning.

**Recommended fix:** create independent flags per analog (immutable flags plus a candidate-local
override record would be safer than copying mutable flags). Add a test that overrides one of two
candidates and asserts the other remains untouched.

### P1 — Describe-and-highlight fallback does not carry highlightable position metadata

**Locations:** `chansu/core/generation.py:75-93`, `chansu/core/generation.py:178-198`

When a position resolves but reaction parsing, execution, attribution, or sanitization fails,
`_describe_fallback()` returns `modified_atom_idx=None`. Its description nevertheless says the
position is highlighted. A UI cannot highlight the site from this `Analog`.

The early “position could not be located” return also skips the loop that assigns parentage, so it
returns `parent_id=""` rather than the compound ID. The existing fallback test checks neither
field.

**Recommended fix:** pass `parent_id`, the requested position ID/locator, and the resolved atom
index (when known) into the fallback. Do not claim “highlighted” when no highlight target exists;
instead expose an explicit unresolved-position flag. Add separate tests for known-site reaction
failure and unlocatable-site failure.

### P1 — A sanitizable product is accepted even when no modification occurred

**Locations:** `chansu/core/generation.py:48-72`, `chansu/core/generation.py:122-151`

The engine trusts `reacting_atom_mapnum` to identify the edited site, but never validates that this
mapped atom or any parent bond/atom actually changed. The identity reaction `[C:1]>>[C:1]` returns a
valid analog whose canonical SMILES equals the parent and whose reported modified site is atom 0.

When `target_atom_idx` is omitted, a product with missing attribution can also be accepted with
`modified_atom_idx=None`; only the targeted path filters missing attribution.

Sanitization is necessary but does not establish that the transformation was applied or attributed
correctly.

**Recommended fix:** validate reaction templates before use, require successful parent attribution
for structural candidates, reject/dedupe products identical to the parent, and compute enough of a
parent/product change set to confirm the declared reacting site participates. Fall back with a
specific reason when the transformation is a no-op or attribution is unavailable. Add direct tests
for correct map attribution, a missing/wrong map number, a deleted mapped atom, and an identity
reaction.

### P1 — Attachment-type compatibility is declared but never enforced

**Locations:** `chansu/core/models.py:62-70`, `chansu/core/models.py:123-138`,
`chansu/core/generation.py:178-198`

Positions declare `attachment_types`, and transformations declare
`applies_to_attachment_types`, but `generate_at_position()` does not compare them. I changed the
loaded transformation's applicability to `['amine_only']` and it still generated a valid product at
a position declared as hydroxyl/secondary alcohol.

This lets a caller bypass the data-driven applicability contract and shifts hidden assumptions
back into reaction matching.

**Recommended fix:** define compatibility semantics explicitly. Usually a nonempty intersection is
required; decide what an empty list means (wildcard or invalid metadata) and encode that choice.
Return a typed/flagged describe-only result for incompatibility. Update the data-only fixture,
which currently omits attachment types, to exercise the intended rule.

### P1 — Built wheels omit the data required by the installed CLI

**Locations:** `chansu/core/loaders.py:28-33`, `pyproject.toml:21-23`

The wheel contains only `chansu/**`; it does not contain `data/config.json`, compounds, or
transformations. In a clean Python 3.12 environment, the installed package resolves its default
data directory to `site-packages/data`, which does not exist. `load_config()` returns `{}` and the
installed `chansu` command exits 2 with “No compound id given...”.

**Recommended fix:** either package default data under a package-owned resource directory and load
it with `importlib.resources`, or make an external data directory a required/configurable runtime
input and remove the implication that the console script works standalone. Add a build-and-install
smoke test that runs the wheel from outside the repository.

### P2 — Reaction cardinality and product selection are hidden engine assumptions

**Locations:** `chansu/core/generation.py:117-129`

The engine always supplies exactly one reactant and always takes `product_set[0]`, silently ignoring
additional products. The `Transformation` schema does not declare “unary reaction, first product is
the desired analog,” and no validation enforces it. A future data entry with multiple reactants,
multiple meaningful products, a counterion, or a differently ordered main product will either fall
back or emit only the first molecule.

This is not a named compound leak, but it is a compound/reaction-shape assumption inside the
supposedly generic engine.

**Recommended fix:** either formally constrain and validate transformation data to one reactant and
one desired product, or add data-driven product-selection semantics. Also set an explicit
`maxProducts` limit so an overly broad template cannot create an uncontrolled product explosion.

### P2 — Loader and model invariants are mostly implicit, producing late or inconsistent failures

**Locations:** `chansu/core/loaders.py:45-137`, `chansu/core/models.py:38-209`

Malformed JSON and missing/wrongly typed fields surface as raw `JSONDecodeError`, `KeyError`,
`TypeError`, or later RDKit errors. Examples include invalid locator index types, filename/embedded
ID mismatches, malformed annotation lists, and invalid enum-like strings such as importance level.
`Analog` can also be instantiated in contradictory states (`valid=True` without a product,
`describe_only=True` and `valid=True`).

**Recommended fix:** add an explicit data-validation boundary with contextual error types and
validate dataclass invariants. Keep reaction authoring errors eligible for describe-only fallback,
but distinguish invalid input data from “a valid template produced no clean candidate.” This makes
UI and adapter error handling predictable.

### P2 — Override “reason recorded” accepts an empty reason and has no candidate-local audit record

**Location:** `chansu/core/models.py:183-188`

`Flag.override("")` and whitespace-only reasons are accepted. The mutable flag stores only the
latest state, not who/when or a separate override event. The current project may not need a full
audit log, but it does require an actual reason and candidate-local behavior.

**Recommended fix:** reject blank reasons and store an immutable override record associated with
the analog/candidate. At minimum test blank, whitespace, non-overridable, and independent-candidate
cases.

### P2 — The current test suite does not lock the stated contracts

**Location:** `tests/test_core.py`

The seven tests are useful smoke tests, but several claims in their comments are stronger than what
they prove:

- The forbidden-token/AST scan is a blacklist. It can catch a few known leaks but cannot prevent a
  branch on `compound.id`, `annotations['class']`, an unlisted functional-group name, or a reaction
  SMARTS assembled indirectly. The positive second-compound test is more valuable, but it covers
  one unambiguous alcohol and reuses one transformation.
- The generation test verifies formula and similarity but not that `modified_atom_idx` equals the
  requested locator. A reaction at the wrong site can have the same formula and pass.
- No tests cover importance gating, overrides, locator ambiguity/validation, transformation
  compatibility, no-op products, missing attribution, sanitization failures, multiple products,
  fallback metadata, loader failures, packaged execution, or any adapter behavior.
- The local-model handoff's tool smoke test accepts either `tool_use` or `end_turn` and never sends
  a tool result back, so it does not verify tool support.

**Recommended test additions, in order:**

1. Adapter conformance tests for plain completion, tool request/result/final response, timeout/error
   normalization, non-stream fallback, and typed streaming finalization.
2. Locator validation tests: invalid SMARTS, negative/out-of-range target index, zero matches,
   multiple matches without policy, and an explicitly selected repeated site.
3. Generation attribution tests on both existing positions, wrong/missing map number, identity
   reaction, invalid product, deduplication, multi-product policy, and fallback metadata.
4. Gate tests for full-region overlap, unresolved region behavior, independent candidate overrides,
   blank override reason, and non-overridable flags.
5. A data-only second compound with repeated motifs and at least two transformations/attachment
   types. This exercises generality rather than relying on a vocabulary blacklist.
6. A wheel smoke test from a temporary environment outside the checkout.

## Generic-engine conclusion

No explicit compound-specific chemistry is currently visible in `chansu/`, which is good. The
abstraction nevertheless does **not** yet fully hold. The engine assumes:

- every declared position has one meaningful first SMARTS match;
- an importance region is represented by one atom;
- a transformation uses one reactant, with the desired molecule as the first product;
- one mapped atom is sufficient to describe the entire edit;
- reaction SMARTS matching is an adequate substitute for declared attachment compatibility.

Those assumptions are not specific to the flagship, but they are specific to a narrow class of
compound data and reaction templates. Either make them explicit, validated constraints of v1, or
extend the data contracts so a new compound can resolve them without engine edits.

## What is working and should be preserved

- Compound identity and transformation details are loaded from data rather than hard-coded into
  generation logic.
- The current configured C3 and C14 positions both resolve and are correctly reported through
  `react_atom_idx` in targeted probes.
- Reaction parse/execution errors degrade to describe-only rather than escaping the public
  generation path.
- Products that are returned structurally go through `Chem.SanitizeMol` and canonical SMILES
  generation.
- Canonical-SMILES deduplication is simple and appropriate once attribution/change validation is
  added.
- The sync, text-only portion of the adapter is small and straightforward to implement.

## Verification performed

- `.venv/bin/python -m pytest -q` — **7 passed**.
- `.venv/bin/python -m chansu.cli` — completed successfully from the checkout.
- Targeted RDKit probes confirmed:
  - C3 requested atom 5 -> reported atom 5;
  - C14 requested atom 27 -> reported atom 27;
  - ambiguous locators select the first match;
  - a negative locator index can raise `IndexError`;
  - an identity reaction is emitted as a valid analog;
  - attachment-type mismatch is ignored;
  - gate flags are shared and overrides leak;
  - fallbacks lose highlight metadata, and the unlocatable fallback loses parentage.
- Built and installed the wheel into a clean temporary Python 3.12 environment; confirmed that the
  wheel omits `data/` and the installed CLI exits 2.

Environment: Python 3.12.13, RDKit 2026.03.3.

## Suggested implementation order for Claude Code

1. Settle the adapter message/tool/stream contracts before implementing a real backend.
2. Define and validate locator semantics, including region-as-set behavior.
3. Make generation validate compatibility, attribution, and actual structural change.
4. Make fallback and gate state candidate-local and metadata-complete.
5. Decide and enforce the v1 reaction cardinality/product-selection constraint.
6. Add contextual loader/model validation.
7. Fix package data and add the clean-wheel smoke test.
8. Expand tests alongside each contract change; keep the existing seven smoke tests.

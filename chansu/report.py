"""Render the grounded reasoning and the design memo (PROJECT.md §13).

Two renderers over the same underlying data, both provenance-tagged:
  * ``render_grounding`` — the Day-3 view: cited targets, liabilities, importance map, and
    liability -> strategy matches.
  * ``render_memo`` — the Day-4 must-ship: the full design memo over an already-computed, possibly
    *reviewed* ``DesignResult`` (ranked, gated, scored candidates).

Rendering is deliberately separate from orchestration: ``design`` (pipeline.py) runs the loop and
returns a result the caller can review — overriding a candidate's gate flag with a recorded reason —
and ``render_memo`` renders exactly that result, so the override survives into the output (the other
half of the two-way gate, PROJECT.md §6). ``design_and_render`` is the one-call convenience for the
CLI. Pure text; the Streamlit UI (Day 5) renders the same data.

A scientific claim is tagged ``[literature — cited]`` only when it carries a real citation source;
otherwise it is rendered honestly as uncited — the renderer never prints a cited tag it can't back.
"""

from __future__ import annotations

from typing import Optional

from rdkit.Chem import Mol

from .core.matching import StrategyMatch, match_strategies
from .core.models import Compound, Flag, Provenance, Strategy, reasoning_tag, tag
from .core.pipeline import Candidate, DesignResult, design
from .core.properties import compute_properties
from .core.scoring import DEFAULT_WEIGHTS
from .reasoning.design_reasoning import DesignReasoning

_LIT = tag(Provenance.LITERATURE)
_HYP = tag(Provenance.HYPOTHESIS)
_COMPUTED = tag(Provenance.COMPUTED)

# Bounded honest failure: the tool only knows the *supplied* library had no match — it says exactly
# that and invents no out-of-scope route (Codex P2; PROJECT.md §6).
_HONEST_FAILURE = (
    "    -> no strategy in the current curated library matches this liability; "
    "the tool declines to over-claim."
)


def _header(title: str) -> list[str]:
    return ["", title, "=" * len(title)]


def _lit(obj) -> str:
    """Provenance for a scientific claim: ``[literature — cited]`` with the source only when a real
    citation source is present; otherwise rendered honestly as uncited. The renderer never emits a
    cited tag it cannot back (Codex P1)."""
    c = getattr(obj, "citation", None)
    if c is not None and c.source:
        return f"{_LIT}  {c.source}"
    return "[uncited · not literature-backed]"


def _identity_lines(compound: Compound) -> list[str]:
    src = " ".join(p for p in (compound.source, compound.source_id) if p) or "(unsourced)"
    lines = [
        f"  Compound         : {compound.name}  ({compound.id})",
        f"  Structure source : {src}   (database record)",
        f"  InChIKey         : {compound.inchikey or '(n/a)'}",
        f"  Canonical SMILES : {compound.smiles}",
    ]
    if compound.annotations.get("class"):
        lines.append(f"  Class (annotation): {compound.annotations['class']}")
    return lines


def _targets_lines(compound: Compound) -> list[str]:
    lines = ["Targets"]
    for t in compound.targets:
        lines.append(f"  - {t.name}   {_lit(t)}")
        lines.append(f"      {t.role}")
    return lines or ["Targets", "  (none curated)"]


def _liabilities_lines(compound: Compound) -> list[str]:
    lines = ["Liabilities"]
    for lib in compound.liabilities:
        lines.append(f"  - {lib.kind}   {_lit(lib)}")
        lines.append(f"      {lib.detail}")
    return lines


def _importance_lines(compound: Compound) -> list[str]:
    lines = ["Importance map (graded, advisory)"]
    for r in compound.importance_map:
        lines.append(f"  - [{r.importance.upper():6s}] {r.locator.label or r.id}   {_lit(r)}")
        lines.append(f"      {r.reason}")
    return lines


def _matched_strategies_lines(compound: Compound, library: list[Strategy]) -> list[str]:
    lines = ["Matched strategies (per liability)"]
    by_liability: dict[str, list[StrategyMatch]] = {}
    for m in match_strategies(compound, library):
        by_liability.setdefault(m.liability.kind, []).append(m)
    for kind, group in by_liability.items():
        lines.append(f"\n  Liability: {kind}")
        if len(group) == 1 and group[0].strategy is None:
            lines.append(_HONEST_FAILURE)
            continue
        for m in group:
            s = m.strategy
            lines.append(f"    -> {s.id}  (precedent: {s.precedent_drug})   {_lit(s)}")
            if m.actionable:
                where = ", ".join(p.label for p in m.actionable_positions)
                how = (
                    f"encoded transformation '{s.transformation_id}' {_HYP}"
                    if s.transformation_id
                    else f"describe-and-highlight (no clean auto-transformation) {_HYP}"
                )
                lines.append(f"         actionable at: {where}  ->  {how}")
            else:
                lines.append(
                    "         relevant, but this compound has no matching attachment point "
                    "(describe / not directly actionable, no site fabricated)"
                )
    return lines


def render_grounding(compound: Compound, library: list[Strategy]) -> str:
    lines: list[str] = []
    lines += _header(f"Compound: {compound.name}  ({compound.id})")
    lines += _identity_lines(compound)[1:]  # drop the duplicate "Compound" line
    lines += _header("Targets")[:1] + _targets_lines(compound)[1:]
    lines += _header("Liabilities")[:1] + _liabilities_lines(compound)[1:]
    lines += _header("Importance map (graded, advisory)")[:1] + _importance_lines(compound)[1:]
    lines += _header("Matched strategies (per liability)")[:1] + _matched_strategies_lines(compound, library)[1:]
    return "\n".join(lines)


def _delta(value: float, parent: float) -> str:
    d = round(value - parent, 2)
    return f"{value} ({'+' if d >= 0 else ''}{d} vs parent)"


def _flag_lines(flags: list[Flag], indent: str) -> list[str]:
    """Render every flag, its current override state, and (when the flag restates a literature
    claim) its citation tag — so the two-way gate is visible and provenance-honest (Codex P1)."""
    lines: list[str] = []
    for f in flags:
        cite = f"   {_LIT}  {f.citation.source}" if getattr(f, "citation", None) and f.citation.source else ""
        lines.append(f"{indent}FLAG [{f.level.value}]: {f.message}{cite}")
        if f.overridden:
            lines.append(f"{indent}    -> OVERRIDDEN by chemist. Reason recorded: {f.override_reason}")
        elif f.overridable:
            lines.append(f"{indent}    -> overridable; the chemist decides and the reason is recorded.")
    return lines


def _candidate_lines(candidate: Candidate, parent_profile, index: int) -> list[str]:
    s = candidate.strategy
    at = f" at {candidate.position_label}" if candidate.position_label else ""
    lines = [f"    [{index}] {s.id}{at}  (precedent: {s.precedent_drug})   {_lit(s)}"]
    lines.append(f"        analog: {candidate.analog.product_smiles}   {_HYP}")
    sc = candidate.score
    lines.append(
        f"        score {sc.total}  = {sc.weights['similarity']}*{sc.similarity}(sim)"
        f" + {sc.weights['ease']}*{sc.ease}(ease)"
        f" + {sc.weights['druglikeness']}*{sc.druglikeness}(druglike)   {_COMPUTED}"
    )
    p = candidate.properties
    lines.append(
        f"        {p['formula']}  MW {_delta(p['mw'], parent_profile.mw)}"
        f"  logP {_delta(p['logp'], parent_profile.logp)}"
        f"  TPSA {_delta(p['tpsa'], parent_profile.tpsa)}   {_COMPUTED}"
    )
    lines += _flag_lines(candidate.flags, "        ")
    return lines


def _described_lines(candidate: Candidate) -> list[str]:
    """A describe-and-highlight candidate: its position, its described edit, and every flag —
    including a high-importance gate flag if the described site is essential (Codex P1)."""
    s = candidate.strategy
    at = f" at {candidate.position_label}" if candidate.position_label else " (no compatible attachment point)"
    lines = [f"    [describe] {s.id}{at}  (precedent: {s.precedent_drug})   {_lit(s)}"]
    lines.append(f"        {candidate.analog.description}   {_HYP}")
    lines += _flag_lines(candidate.flags, "        ")
    return lines


def _rationale_lines(liability_kind: str, group: list[Candidate], reasoning: Optional[DesignReasoning]) -> list[str]:
    """The model's per-strategy rationale for this liability, tagged ``[reasoning — <model>]``. The
    tag names the model that reasoned (from the adapter) and stands alone — the precedent it reasons
    from carries its own ``[literature — cited]`` on the candidate lines below."""
    if reasoning is None or not reasoning.available:
        return []
    lines: list[str] = []
    seen: set[str] = set()
    for c in group:
        if c.strategy.id in seen:
            continue
        text = reasoning.rationale_for(liability_kind, c.strategy.id)
        if not text:
            continue
        seen.add(c.strategy.id)
        lines.append(f"    Why {c.strategy.id} applies:   {reasoning_tag(reasoning.model_name)}")
        for para in text.split("\n"):
            if para.strip():
                lines.append(f"        {para.strip()}")
    return lines


def _reasoning_checks_lines(reasoning: DesignReasoning) -> list[str]:
    """The reasoning-checks panel (PROJECT.md §6; Luke's transparency directive): every reasoning
    call's pass/decline/why, never silently omitted. A decline is not a bug to hide — surfacing
    'the model's own safety layer declined this one (bio)' is a live trust-boundary demonstration."""
    checks = reasoning.checks
    if not checks:
        return []
    passed = sum(1 for c in checks if c.passed)
    declined = [c for c in checks if not c.passed]
    # Categories among declines (e.g. {"bio"}); a refusal without a category still counts.
    cats = sorted({c.category for c in declined if c.category})
    cat_note = f" ({', '.join(cats)})" if cats else ""
    lines = [f"  Reasoning checks: {passed} of {len(checks)} calls passed"]
    if declined:
        lines[0] += f"; {len(declined)} declined by the model's own safety layer{cat_note}."
        lines.append("  (declines are shown, not hidden. This is the trust boundary working, not a failure.)")
    else:
        lines[0] += "."
    for c in checks:
        if c.passed:
            lines.append(f"    - {c.label}: passed")
        else:
            why = f"{c.stop_reason}" + (f"/{c.category}" if c.category else "")
            out = f", output_tokens={c.output_tokens}" if c.output_tokens is not None else ""
            lines.append(f"    - {c.label}: declined ({why}{out})")
    return lines


def render_memo(
    compound: Compound, mol: Mol, result: DesignResult, reasoning: Optional[DesignReasoning] = None
) -> str:
    """Render an already-computed ``DesignResult`` (see ``design``), optionally with the reasoning
    model's runtime analysis (see ``reason_over_design``). Any gate override the caller recorded on
    the result is rendered here — orchestration and rendering are separate so the override survives
    to the output (PROJECT.md §6). ``reasoning`` is optional: absent or unavailable, the memo is the
    deterministic design; present, the model's per-match rationale and synthesis appear, each tagged
    ``[reasoning — <model>]``."""
    parent = compute_properties(mol)

    lines = _header(f"DESIGN MEMO · {compound.name}  ({compound.id})")
    lines.append("  Every claim is provenance-tagged. Computed facts, cited literature, model reasoning,")
    lines.append("  and wet-lab hypotheses are kept visibly distinct. Candidates are hypotheses for wet-lab")
    lines.append("  validation, never predictions presented as fact (PROJECT.md §6).")
    lines += [""] + _identity_lines(compound)

    lines += _header("Grounding")
    lines += _targets_lines(compound) + [""] + _liabilities_lines(compound) + [""] + _importance_lines(compound)

    lines += _header("Scoring rubric (transparent)")
    w = DEFAULT_WEIGHTS
    lines.append(
        f"  score = {w['similarity']}*similarity-to-parent + {w['ease']}*synthetic-ease"
        f" + {w['druglikeness']}*druglikeness    (all {_COMPUTED}, each in 0..1)"
    )
    lines.append("  Weights are shown so the ranking is legible. Flags are surfaced beside the score,")
    lines.append("  never silently folded into it.")

    lines += _header("Design candidates (per liability)")
    by_liability: dict[str, list[Candidate]] = {}
    for c in result.candidates:
        by_liability.setdefault(c.liability, []).append(c)
    unaddressed = {lib.kind for lib in result.unaddressed}

    for lib in compound.liabilities:
        lines.append(f"\n  Liability: {lib.kind}   {_lit(lib)}")
        if lib.kind in unaddressed:
            lines.append(_HONEST_FAILURE)
            continue
        group = by_liability.get(lib.kind, [])
        lines += _rationale_lines(lib.kind, group, reasoning)
        valid = sorted(
            [c for c in group if c.analog.valid and c.score is not None],
            key=lambda c: c.score.total,
            reverse=True,
        )
        described = [c for c in group if c.analog.describe_only]
        for i, candidate in enumerate(valid, 1):
            lines += _candidate_lines(candidate, parent, i)
        for candidate in described:
            lines += _described_lines(candidate)

    if reasoning is not None:
        lines += _header("Design synthesis")
        if reasoning.available:
            mode = "compound-specific" if reasoning.depth == "compound" else "strategy-level (compound-agnostic)"
            lines.append(f"  Reasoning mode: {mode}.")
            lines += _reasoning_checks_lines(reasoning)
            if reasoning.narrative:
                if reasoning.note:
                    lines.append(f"  note: {reasoning.note}")
                lines.append(f"  {reasoning_tag(reasoning.model_name)}")
                for para in reasoning.narrative.split("\n"):
                    lines.append(f"  {para.strip()}" if para.strip() else "")
            else:
                lines.append("  (the model produced no synthesis for this run.)")
                if reasoning.note:
                    lines.append(f"  diagnostic: {reasoning.note}")
        else:
            lines.append(f"  (reasoning not run. {reasoning.note}.)")
            lines.append("  Showing the deterministic design; configure a reasoning backend for the reasoned memo.")

    lines += _header("Validation & honest limits")
    lines.append("  Candidates are grounded hypotheses; the tool never predicts binding, toxicity, or efficacy,")
    lines.append("  and every candidate needs wet-lab validation. High-importance edits are flagged, not blocked.")
    lines.append("  the tool surfaces the risk and the chemist overrides with a recorded reason (PROJECT.md §6).")
    # A compound may carry an author's validation narrative in data. It is labeled as such and NOT
    # presented as pipeline-verified — free-form prose is never laundered into a checked claim.
    note = compound.annotations.get("validation_note")
    if note:
        lines.append("")
        lines.append("  Author's validation narrative (data-provided; NOT verified against this run):")
        for paragraph in note.split("\n"):
            lines.append(f"    {paragraph}")
    return "\n".join(lines)


def design_and_render(compound: Compound, mol: Mol, library: list[Strategy], data_dir=None) -> str:
    """Convenience: run the loop and render it in one call (the CLI path). To render a *reviewed*
    gate — override a flag before rendering — call ``design`` then ``render_memo`` on the result."""
    return render_memo(compound, mol, design(compound, mol, library, data_dir=data_dir))

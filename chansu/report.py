"""Render the grounded reasoning and the design memo (PROJECT.md §13).

Two renderers over the same underlying data, both provenance-tagged:
  * ``render_grounding`` — the Day-3 view: cited targets, liabilities, importance map, and
    liability -> strategy matches.
  * ``render_memo`` — the Day-4 must-ship: the full design memo, adding ranked, gated, scored
    candidates and honest-failure / validation framing.

Pure text; the Streamlit UI (Day 5) renders the same data.
"""

from __future__ import annotations

from rdkit.Chem import Mol

from .core.matching import StrategyMatch, match_strategies
from .core.models import Compound, Provenance, Strategy, tag
from .core.pipeline import Candidate, design
from .core.properties import compute_properties
from .core.scoring import DEFAULT_WEIGHTS

_LIT = tag(Provenance.LITERATURE)
_HYP = tag(Provenance.HYPOTHESIS)
_OOS = tag(Provenance.OUT_OF_SCOPE)
_COMPUTED = tag(Provenance.COMPUTED)


def _header(title: str) -> list[str]:
    return ["", title, "=" * len(title)]


def _cite(obj) -> str:
    return obj.citation.source if getattr(obj, "citation", None) else "(uncited)"


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
        lines.append(f"  - {t.name}   {_LIT}  {_cite(t)}")
        lines.append(f"      {t.role}")
    return lines or ["Targets", "  (none curated)"]


def _liabilities_lines(compound: Compound) -> list[str]:
    lines = ["Liabilities"]
    for lib in compound.liabilities:
        lines.append(f"  - {lib.kind}   {_LIT}  {_cite(lib)}")
        lines.append(f"      {lib.detail}")
    return lines


def _importance_lines(compound: Compound) -> list[str]:
    lines = ["Importance map (graded, advisory)"]
    for r in compound.importance_map:
        lines.append(f"  - [{r.importance.upper():6s}] {r.locator.label or r.id}   {_LIT}  {_cite(r)}")
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
            lines.append(
                f"    -> no well-precedented strategy applies; flag for review / may route to "
                f"formulation-delivery {_OOS}. The tool declines to over-claim."
            )
            continue
        for m in group:
            s = m.strategy
            lines.append(f"    -> {s.id}  (precedent: {s.precedent_drug})   {_LIT}  {_cite(s)}")
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
                    "(describe / not directly actionable — no site fabricated)"
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


def _candidate_lines(candidate: Candidate, parent_profile, index: int) -> list[str]:
    s = candidate.strategy
    lines = [f"    [{index}] {s.id}  (precedent: {s.precedent_drug})   {_LIT}  {_cite(s)}"]
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
    for f in candidate.flags:
        lines.append(
            f"        FLAG [{f.level.value}]: {f.message}"
            " — overridable; the chemist decides and the reason is recorded."
        )
    return lines


def render_memo(compound: Compound, mol: Mol, library: list[Strategy]) -> str:
    result = design(compound, mol, library)
    parent = compute_properties(mol)

    lines = _header(f"DESIGN MEMO — {compound.name}  ({compound.id})")
    lines.append("  Every claim is provenance-tagged. Candidates are hypotheses for wet-lab")
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
        lines.append(f"\n  Liability: {lib.kind}   {_LIT}  {_cite(lib)}")
        if lib.kind in unaddressed:
            lines.append(
                f"    -> no well-precedented strategy applies; flag for review / may route to "
                f"formulation-delivery {_OOS}. The tool declines to over-claim."
            )
            continue
        group = by_liability.get(lib.kind, [])
        valid = sorted(
            [c for c in group if c.analog.valid and c.score is not None],
            key=lambda c: c.score.total,
            reverse=True,
        )
        described = [c for c in group if c.analog.describe_only]
        for i, candidate in enumerate(valid, 1):
            lines += _candidate_lines(candidate, parent, i)
        for candidate in described:
            lines.append(
                f"    [describe] {candidate.strategy.id}  "
                f"(precedent: {candidate.strategy.precedent_drug})   {_LIT}  {_cite(candidate.strategy)}"
            )
            lines.append(f"        {candidate.strategy.concept}   {_HYP}")
            lines.append(f"        (not auto-generated — {candidate.analog.error})")

    lines += _header("Validation & honest limits")
    lines.append("  Candidates are grounded hypotheses; the tool never predicts binding, toxicity, or efficacy,")
    lines.append("  and every candidate needs wet-lab validation. High-importance edits are flagged, not blocked —")
    lines.append("  the tool surfaces the risk and the chemist overrides with a recorded reason (PROJECT.md §6).")
    # A compound may carry its own validation narrative in data (never hard-coded here).
    note = compound.annotations.get("validation_note")
    if note:
        lines.append("")
        for paragraph in note.split("\n"):
            lines.append(f"  {paragraph}")
    return "\n".join(lines)

"""Render the grounded, provenance-tagged reasoning for a compound (PROJECT.md §13).

Given a compound plus the strategy library, produce the Day-3 deliverable: cited targets,
liabilities, and importance map, and the liability -> strategy matches — every claim carries a
provenance tag, and honest failure is shown where no strategy applies. Pure text; the Streamlit
UI (Day 5) renders the same underlying data.
"""

from __future__ import annotations

from .core.matching import StrategyMatch, match_strategies
from .core.models import Compound, Provenance, Strategy, tag

_LIT = tag(Provenance.LITERATURE)
_HYP = tag(Provenance.HYPOTHESIS)
_OOS = tag(Provenance.OUT_OF_SCOPE)


def _header(title: str) -> list[str]:
    return ["", title, "=" * len(title)]


def render_grounding(compound: Compound, library: list[Strategy]) -> str:
    lines: list[str] = []

    lines += _header(f"Compound: {compound.name}  ({compound.id})")
    src = " ".join(p for p in (compound.source, compound.source_id) if p) or "(unsourced)"
    lines.append(f"  Structure source : {src}   (database record)")
    lines.append(f"  InChIKey         : {compound.inchikey or '(n/a)'}")
    lines.append(f"  Canonical SMILES : {compound.smiles}")
    if compound.annotations.get("class"):
        lines.append(f"  Class (annotation): {compound.annotations['class']}")

    lines += _header("Targets")
    for t in compound.targets:
        cite = t.citation.source if t.citation else "(uncited)"
        lines.append(f"  - {t.name}   {_LIT}")
        lines.append(f"      {t.role}")
        lines.append(f"      cite: {cite}")
    if not compound.targets:
        lines.append("  (none curated)")

    lines += _header("Liabilities")
    for lib in compound.liabilities:
        cite = lib.citation.source if lib.citation else "(uncited)"
        lines.append(f"  - {lib.kind}   {_LIT}")
        lines.append(f"      {lib.detail}")
        lines.append(f"      cite: {cite}")

    lines += _header("Importance map (graded, advisory)")
    for r in compound.importance_map:
        cite = r.citation.source if r.citation else "(uncited)"
        lines.append(f"  - [{r.importance.upper():6s}] {r.locator.label or r.id}   {_LIT}")
        lines.append(f"      {r.reason}")
        lines.append(f"      cite: {cite}")

    lines += _header("Matched strategies (per liability)")
    matches = match_strategies(compound, library)
    by_liability: dict[str, list[StrategyMatch]] = {}
    for m in matches:
        by_liability.setdefault(m.liability.kind, []).append(m)

    for kind, group in by_liability.items():
        lines.append(f"\n  Liability: {kind}")
        if len(group) == 1 and group[0].strategy is None:
            # Honest failure — nothing in the precedent library addresses this class.
            lines.append(
                f"    -> no well-precedented strategy applies; flag for review / may route to "
                f"formulation-delivery {_OOS}. The tool declines to over-claim."
            )
            continue
        for m in group:
            s = m.strategy
            cite = s.citation.source if s and s.citation else ""
            lines.append(f"    -> {s.id}  (precedent: {s.precedent_drug})   {_LIT}")
            lines.append(f"         cite: {cite}")
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

    return "\n".join(lines)

"""The full design loop (BUILD_PLAN.md DAY 4): compound -> ranked, gated, scored candidates.

For each liability, match precedent strategies; for each strategy that has an encoded
transformation and an actionable position, generate a validated analog (RDKit-sanitized,
two-way-gate flags attached) and score it on the transparent rubric; strategies that are
relevant but can't be cleanly generated (no encoded transformation, or no matching attachment
point) become describe-and-highlight candidates — one per actionable position, each gated the
same way. Liabilities with no precedented strategy are returned as honest failures — the loop
never fabricates one (PROJECT.md §6, §8).

Generic: no compound knowledge here. Everything specific to a compound is read from its data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rdkit import Chem
from rdkit.Chem import Mol

from .generation import generate_at_position
from .loaders import load_transformation
from .matching import match_strategies
from .models import Analog, Compound, Flag, Liability, ModifiablePosition, Strategy
from .scoring import ScoreBreakdown, score


@dataclass
class Candidate:
    """One design idea: a strategy applied (or proposed) against a liability at a position.

    ``position_id`` / ``position_label`` make the site first-class so a described or valid
    candidate is always traceable to the exact handle it was proposed at (both are None only for
    the "no matching attachment point" case, where there is genuinely no site)."""

    liability: str
    strategy: Strategy
    analog: Analog                      # validated structure or describe-and-highlight
    position_id: Optional[str] = None
    position_label: Optional[str] = None
    score: Optional[ScoreBreakdown] = None
    properties: Optional[dict] = None   # [computed] profile of the analog, when valid

    @property
    def flags(self) -> list[Flag]:
        return self.analog.flags


@dataclass
class DesignResult:
    compound_id: str
    candidates: list[Candidate] = field(default_factory=list)
    unaddressed: list[Liability] = field(default_factory=list)  # honest failure: no strategy


def _describe_candidate(
    liability: str,
    strategy: Strategy,
    mol: Mol,
    compound: Compound,
    reason: str,
    position: Optional[ModifiablePosition] = None,
) -> Candidate:
    # Reuse the describe-don't-break analog. When the proposal is at a known position, resolve its
    # atom (to highlight) and run the SAME importance gate a generated analog gets — a described
    # edit at a high-importance region must still be flagged.
    from .generation import _describe_fallback, importance_gate_flags, resolve_position

    atom_idx = resolve_position(mol, position.locator) if position is not None else None
    analog = _describe_fallback(
        _StrategyAsTransformation(strategy),
        position.label if position is not None else None,
        reason,
        parent_id=compound.id,
        modified_atom_idx=atom_idx,
    )
    if atom_idx is not None:
        analog.flags.extend(importance_gate_flags(compound, mol, atom_idx))
    return Candidate(
        liability=liability,
        strategy=strategy,
        analog=analog,
        position_id=position.id if position is not None else None,
        position_label=position.label if position is not None else None,
    )


class _StrategyAsTransformation:
    """Adapt a Strategy to the (id, name) shape ``_describe_fallback`` reads — so a describe-only
    candidate names its strategy, without giving generation a real transformation. ``id`` is None:
    there is no transformation, so the analog's ``transformation_id`` stays honestly empty."""

    def __init__(self, strategy: Strategy) -> None:
        self.id = None
        self.name = strategy.concept


def design(
    compound: Compound, mol: Mol, library: list[Strategy], data_dir: Optional[Path] = None
) -> DesignResult:
    """Run the full design loop over a *reviewed-able* result. Rendering is separate (report.py):
    a caller can override a candidate's gate flag on the returned result before it is rendered, and
    that override survives (PROJECT.md §6). ``data_dir`` overrides where transformations load from,
    so a compound/library loaded from an override directory resolves its transformations there too."""
    result = DesignResult(compound_id=compound.id)
    for match in match_strategies(compound, library):
        strategy = match.strategy
        if strategy is None:
            result.unaddressed.append(match.liability)
            continue

        if strategy.transformation_id and match.actionable:
            try:
                transformation = load_transformation(strategy.transformation_id, override=data_dir)
            except (OSError, ValueError, KeyError) as exc:
                # Bad/missing/malformed transformation data must not abort the whole loop: degrade
                # this one strategy to describe-and-highlight (still gated, per position) and keep
                # serving every other liability (PROJECT.md §8).
                for position in match.actionable_positions:
                    result.candidates.append(
                        _describe_candidate(
                            match.liability.kind, strategy, mol, compound,
                            f"encoded transformation could not be loaded ({exc})", position=position,
                        )
                    )
                continue
            for position in match.actionable_positions:
                for analog in generate_at_position(compound, mol, transformation, position):
                    candidate = Candidate(
                        liability=match.liability.kind,
                        strategy=strategy,
                        analog=analog,
                        position_id=position.id,
                        position_label=position.label,
                    )
                    if analog.valid and analog.product_smiles:
                        analog_mol = Chem.MolFromSmiles(analog.product_smiles)
                        candidate.score = score(mol, analog_mol)
                        candidate.properties = _profile(analog_mol)
                    result.candidates.append(candidate)
        elif match.actionable:
            # Relevant and actionable, but no encoded transformation: emit one described candidate
            # per actionable position, each gated — never collapse the positions into one.
            for position in match.actionable_positions:
                result.candidates.append(
                    _describe_candidate(
                        match.liability.kind, strategy, mol, compound,
                        "no encoded transformation is available for this strategy", position=position,
                    )
                )
        else:
            # Relevant but no compatible attachment point anywhere — genuinely no site to name.
            result.candidates.append(
                _describe_candidate(
                    match.liability.kind, strategy, mol, compound,
                    "strategy is relevant but this compound has no matching attachment point",
                )
            )
    return result


def _profile(analog_mol: Mol) -> dict:
    from .properties import compute_properties

    return compute_properties(analog_mol).as_dict()


def ranked_valid(result: DesignResult) -> list[Candidate]:
    """Valid, scored candidates, best score first."""
    valid = [c for c in result.candidates if c.analog.valid and c.score is not None]
    return sorted(valid, key=lambda c: c.score.total, reverse=True)

"""The full design loop (BUILD_PLAN.md DAY 4): compound -> ranked, gated, scored candidates.

For each liability, match precedent strategies; for each strategy that has an encoded
transformation and an actionable position, generate a validated analog (RDKit-sanitized,
two-way-gate flags attached) and score it on the transparent rubric; strategies that are
relevant but can't be cleanly generated (complex conjugation, or no matching attachment point)
become describe-and-highlight candidates. Liabilities with no precedented strategy are returned
as honest failures — the loop never fabricates one (PROJECT.md §6, §8).

Generic: no compound knowledge here. Everything specific to a compound is read from its data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from rdkit import Chem
from rdkit.Chem import Mol

from .generation import generate_at_position
from .loaders import load_transformation
from .matching import match_strategies
from .models import Analog, Compound, Flag, Liability, Strategy
from .scoring import ScoreBreakdown, score


@dataclass
class Candidate:
    """One design idea: a strategy applied (or proposed) against a liability."""

    liability: str
    strategy: Strategy
    analog: Analog                      # validated structure or describe-and-highlight
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


def _describe_candidate(liability: str, strategy: Strategy, mol: Mol, compound: Compound, reason: str) -> Candidate:
    from .generation import _describe_fallback  # reuse the describe-don't-break analog

    analog = _describe_fallback(
        # a Transformation-shaped stand-in isn't needed: pass the strategy's name via a light shim
        _StrategyAsTransformation(strategy), None, reason, parent_id=compound.id
    )
    return Candidate(liability=liability, strategy=strategy, analog=analog)


class _StrategyAsTransformation:
    """Adapt a Strategy to the (id, name) shape ``_describe_fallback`` reads — so a describe-only
    candidate names its strategy, without giving generation a real transformation."""

    def __init__(self, strategy: Strategy) -> None:
        self.id = strategy.id
        self.name = strategy.concept


def design(compound: Compound, mol: Mol, library: list[Strategy]) -> DesignResult:
    result = DesignResult(compound_id=compound.id)
    for match in match_strategies(compound, library):
        strategy = match.strategy
        if strategy is None:
            result.unaddressed.append(match.liability)
            continue

        if strategy.transformation_id and match.actionable:
            transformation = load_transformation(strategy.transformation_id)
            for position in match.actionable_positions:
                for analog in generate_at_position(compound, mol, transformation, position):
                    candidate = Candidate(liability=match.liability.kind, strategy=strategy, analog=analog)
                    if analog.valid and analog.product_smiles:
                        analog_mol = Chem.MolFromSmiles(analog.product_smiles)
                        candidate.score = score(mol, analog_mol)
                        candidate.properties = _profile(analog_mol)
                    result.candidates.append(candidate)
        elif match.actionable:
            result.candidates.append(
                _describe_candidate(
                    match.liability.kind, strategy, mol, compound,
                    "no encoded transformation for this strategy yet (complex conjugation)",
                )
            )
        else:
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

"""Transparent candidate scoring (PROJECT.md §8 step 8 — "scores, ranks, and explains ... on a
transparent rubric").

Option A: a weighted sum of a few deterministic [computed] signals, every weight shown so the
chemist can see exactly why a candidate ranks where it does. Nothing here is a prediction of
activity — it is druglikeness / make-ability / similarity math (PROJECT.md §6). Flags (a
high-importance edit, a describe-only fallback) are surfaced by the memo alongside the score,
never silently folded into it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from rdkit.Chem import Mol

from .properties import compute_properties, tanimoto_similarity

# Keeping the active region intact matters most for a natural-product analog, so similarity
# carries the largest weight. Weights are data, shown in the memo, and easy to retune.
DEFAULT_WEIGHTS = {"similarity": 0.5, "ease": 0.25, "druglikeness": 0.25}
_COMPONENTS = ("similarity", "ease", "druglikeness")


def _validate_weights(weights: dict) -> None:
    """A weight set must be exactly the three components, each a finite value in [0, 1], summing
    to 1 — otherwise ``total`` would silently leave its documented [0, 1] range and corrupt the
    ranking. Fail loudly at the boundary instead (Codex P2)."""
    missing = [k for k in _COMPONENTS if k not in weights]
    extra = [k for k in weights if k not in _COMPONENTS]
    if missing or extra:
        raise ValueError(f"weights must be exactly {set(_COMPONENTS)} (missing={missing}, extra={extra})")
    for k in _COMPONENTS:
        v = weights[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0.0 <= v <= 1.0:
            raise ValueError(f"weight {k!r} must be a finite number in [0, 1], got {v!r}")
    if abs(sum(weights[k] for k in _COMPONENTS) - 1.0) > 1e-9:
        raise ValueError(f"weights must sum to 1.0, got {sum(weights[k] for k in _COMPONENTS)}")


@dataclass
class ScoreBreakdown:
    """Every component is [computed] and in [0, 1]; ``total`` is their weighted sum."""

    similarity: float          # Tanimoto to parent — active core retained
    ease: float                # from synthetic-accessibility (1 easy .. 10 hard)
    druglikeness: float        # fraction of {Lipinski, Veber} passed
    total: float
    weights: dict = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    def as_dict(self) -> dict:
        return {
            "similarity": self.similarity,
            "ease": self.ease,
            "druglikeness": self.druglikeness,
            "total": self.total,
            "weights": self.weights,
        }


def score(parent: Mol, analog: Mol, weights: dict = DEFAULT_WEIGHTS) -> ScoreBreakdown:
    _validate_weights(weights)
    profile = compute_properties(analog)
    # Round each component first, then compute the total from those rounded values, so the
    # weighted-sum equation the memo prints reproduces the stored total exactly at the shown
    # precision (Codex P2: the displayed terms must equal the displayed total).
    similarity = round(tanimoto_similarity(parent, analog), 3)
    ease = round(max(0.0, min(1.0, (10.0 - profile.sa_score) / 9.0)), 3)
    druglikeness = round((int(profile.lipinski_pass) + int(profile.veber_pass)) / 2.0, 3)
    total = round(
        weights["similarity"] * similarity
        + weights["ease"] * ease
        + weights["druglikeness"] * druglikeness,
        3,
    )
    return ScoreBreakdown(
        similarity=similarity,
        ease=ease,
        druglikeness=druglikeness,
        total=total,
        weights=dict(weights),
    )

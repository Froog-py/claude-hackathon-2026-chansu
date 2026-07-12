"""Transparent candidate scoring (PROJECT.md §8 step 8 — "scores, ranks, and explains ... on a
transparent rubric").

Option A: a weighted sum of a few deterministic [computed] signals, every weight shown so the
chemist can see exactly why a candidate ranks where it does. Nothing here is a prediction of
activity — it is druglikeness / make-ability / similarity math (PROJECT.md §6). Flags (a
high-importance edit, a describe-only fallback) are surfaced by the memo alongside the score,
never silently folded into it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rdkit.Chem import Mol

from .properties import compute_properties, tanimoto_similarity

# Keeping the active region intact matters most for a natural-product analog, so similarity
# carries the largest weight. Weights are data, shown in the memo, and easy to retune.
DEFAULT_WEIGHTS = {"similarity": 0.5, "ease": 0.25, "druglikeness": 0.25}


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
    similarity = tanimoto_similarity(parent, analog)
    profile = compute_properties(analog)
    ease = max(0.0, min(1.0, (10.0 - profile.sa_score) / 9.0))
    druglikeness = (int(profile.lipinski_pass) + int(profile.veber_pass)) / 2.0
    total = (
        weights["similarity"] * similarity
        + weights["ease"] * ease
        + weights["druglikeness"] * druglikeness
    )
    return ScoreBreakdown(
        similarity=round(similarity, 3),
        ease=round(ease, 3),
        druglikeness=round(druglikeness, 3),
        total=round(total, 3),
        weights=dict(weights),
    )

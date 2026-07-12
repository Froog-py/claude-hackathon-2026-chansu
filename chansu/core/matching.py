"""Match a compound's liabilities to precedent-backed strategies (PROJECT.md §4 step 5, §6).

Deterministic and generic: a strategy *addresses* a liability if its ``liability_classes``
include the liability's ``kind``; it is *actionable* on the compound if a modifiable position
offers a compatible attachment type. When no strategy addresses a liability, that is surfaced
as honest failure — the tool declines to over-claim, it never invents a strategy.

Every match is precedent-backed and carries the strategy's real Citation. No RDKit here —
matching is over declared roles (liability class, attachment type), not structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import Compound, Liability, ModifiablePosition, Strategy


@dataclass
class StrategyMatch:
    """One liability paired with one applicable strategy (or ``strategy=None`` when nothing in
    the library addresses that liability class)."""

    liability: Liability
    strategy: Optional[Strategy]
    actionable_positions: list[ModifiablePosition] = field(default_factory=list)

    @property
    def actionable(self) -> bool:
        """The strategy applies AND the compound has a position with a compatible attachment
        type. If False with a strategy set, the strategy is relevant but its attachment point
        is absent (describe / route, do not fabricate a site)."""
        return self.strategy is not None and bool(self.actionable_positions)


def _positions_for(strategy: Strategy, compound: Compound) -> list[ModifiablePosition]:
    wanted = set(strategy.attachment_types)
    return [p for p in compound.modifiable_positions if wanted & set(p.attachment_types)]


def match_strategies(compound: Compound, library: list[Strategy]) -> list[StrategyMatch]:
    """One StrategyMatch per (liability, applicable strategy); one with ``strategy=None`` for
    any liability that no library strategy addresses (honest failure)."""
    matches: list[StrategyMatch] = []
    for liability in compound.liabilities:
        applicable = [s for s in library if liability.kind in s.liability_classes]
        if not applicable:
            matches.append(StrategyMatch(liability=liability, strategy=None))
            continue
        for strategy in applicable:
            matches.append(
                StrategyMatch(
                    liability=liability,
                    strategy=strategy,
                    actionable_positions=_positions_for(strategy, compound),
                )
            )
    return matches

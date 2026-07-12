"""The generic data-model spine (PROJECT.md §7).

Each type is a *role*, not a chemical. A compound is a fully-populated set of these
roles loaded from data. This module is intentionally dependency-free (no RDKit): it is
the framework-agnostic contract that the rest of the core, the reasoning layer, and any
future UI all speak. Nothing here knows about any specific compound.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Provenance(str, Enum):
    """Every claim the tool emits carries exactly one of these tags (PROJECT.md §6)."""

    COMPUTED = "computed"
    LITERATURE = "literature"          # rendered as "cited" — requires a real Citation
    HYPOTHESIS = "hypothesis"          # needs wet-lab validation
    OUT_OF_SCOPE = "out_of_scope"      # e.g. formulation / delivery


_PROVENANCE_TAGS = {
    Provenance.COMPUTED: "[computed]",
    Provenance.LITERATURE: "[literature — cited]",
    Provenance.HYPOTHESIS: "[hypothesis — needs wet-lab validation]",
    Provenance.OUT_OF_SCOPE: "[out of scope]",
}


def tag(provenance: Provenance) -> str:
    """Human-readable provenance tag for output (PROJECT.md §6)."""
    return _PROVENANCE_TAGS[provenance]


@dataclass(frozen=True)
class Citation:
    """A literature reference. Never fabricated — every field must trace to a real source.

    A ``Provenance.LITERATURE`` claim is only honest when it carries one of these.
    """

    label: str
    source: Optional[str] = None   # DOI / PMID / URL
    note: Optional[str] = None


@dataclass
class StructureLocator:
    """A data-driven pointer at an atom/region, resolved by the engine against the RDKit
    mol. Keeps atom indices out of the data and compound knowledge out of the engine:
    the engine resolves ``smarts`` and selects ``target_atom`` from the match tuple.
    """

    smarts: str
    target_atom: int = 0           # index within the SMARTS match tuple to select
    label: Optional[str] = None


@dataclass
class ModifiablePosition:
    """A site where a handle can attach, with AI-suggested rationale (PROJECT.md §7)."""

    id: str
    label: str
    locator: StructureLocator
    attachment_types: list[str] = field(default_factory=list)
    rationale: Optional[str] = None


@dataclass
class ImportanceRegion:
    """Graded, advisory annotation of a region's importance to activity (PROJECT.md §7).

    Curated from literature for the flagship (Day 3), not computed. ``importance`` is
    "high" | "medium" | "low". A high region is *flagged, not forbidden* on edit.
    """

    id: str
    locator: StructureLocator
    importance: str
    reason: str
    citation: Optional[Citation] = None


@dataclass
class Target:
    """A biological target. A compound may have several (PROJECT.md §7)."""

    name: str
    role: Optional[str] = None
    citation: Optional[Citation] = None


@dataclass
class Liability:
    """Any medicinal-chemistry deficiency (PROJECT.md §7): toxicity, poor distribution,
    poor solubility, rapid clearance, insufficient potency, size, ..."""

    kind: str
    detail: Optional[str] = None
    citation: Optional[Citation] = None


@dataclass
class Strategy:
    """A precedent-backed fix for a *class* of liability (PROJECT.md §7). Because it keys
    on liability/attachment *type*, it is reusable across compounds — this is the moat.
    Authored Day 2; every entry requires a real precedent drug and Citation.
    """

    id: str
    concept: str
    mechanism: str
    precedent_drug: str
    citation: Citation
    liability_classes: list[str] = field(default_factory=list)
    attachment_types: list[str] = field(default_factory=list)
    # Encoded transformation that realizes this strategy; None -> describe-and-highlight only
    # (for strategies whose chemistry — glycosylation, conjugation — is too complex to auto-emit).
    transformation_id: Optional[str] = None


@dataclass
class Transformation:
    """An encoded transformation template (PROJECT.md §8): a reaction applied only at
    identified positions. Lives in data; the engine never invents molecules.

    ``reacting_atom_mapnum`` is the atom-map number in ``reaction_smarts`` whose parent
    site the engine tracks (via RDKit ``react_atom_idx``) to attribute a product to a
    position.
    """

    id: str
    name: str
    reaction_smarts: str
    reacting_atom_mapnum: int
    applies_to_attachment_types: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class Compound:
    """A structure plus its role annotations (PROJECT.md §7). Class is annotation, never
    logic. ``smiles`` is canonical and RDKit-validated at load time.

    ``importance_map``, ``targets``, and ``liabilities`` are populated from literature
    (Day 3) with real citations; they are empty for a freshly-loaded structure.
    """

    id: str
    name: str
    smiles: str
    source: Optional[str] = None       # e.g. "PubChem"
    source_id: Optional[str] = None    # e.g. "CID 9547215"
    inchikey: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    annotations: dict = field(default_factory=dict)   # class, notes — annotation only
    modifiable_positions: list[ModifiablePosition] = field(default_factory=list)
    importance_map: list[ImportanceRegion] = field(default_factory=list)
    targets: list[Target] = field(default_factory=list)
    liabilities: list[Liability] = field(default_factory=list)


class FlagLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCK = "block"


@dataclass
class Flag:
    """One half of the two-way gate (PROJECT.md §6): the tool surfaces a concern but never
    silently blocks or silently allows. A flag is overridable; the override is recorded.

    When a flag restates a literature-derived claim (e.g. a high-importance region), it carries
    the source region's id and Citation so the claim can be rendered provenance-tagged rather
    than as untagged free-form text.
    """

    code: str
    level: FlagLevel
    message: str
    overridable: bool = True
    overridden: bool = False
    override_reason: Optional[str] = None
    region_id: Optional[str] = None
    citation: Optional[Citation] = None

    def override(self, reason: str) -> None:
        """Record a human override (PROJECT.md §6). A real, non-empty reason is required —
        "the override is recorded" is meaningless with a blank one."""
        if not self.overridable:
            raise ValueError(f"Flag {self.code!r} is not overridable")
        if not reason or not reason.strip():
            raise ValueError("override reason must be a non-empty string")
        self.overridden = True
        self.override_reason = reason


@dataclass
class Analog:
    """A candidate modification (PROJECT.md §8). Either a validated structure
    (``product_smiles`` set, ``valid`` True) or a describe-don't-break fallback
    (``describe_only`` True) — never a broken molecule presented as real.
    """

    parent_id: str
    transformation_id: Optional[str]   # None when the candidate is a describe-only proposal
    product_smiles: Optional[str]
    valid: bool
    modified_atom_idx: Optional[int] = None
    provenance: Provenance = Provenance.HYPOTHESIS
    flags: list[Flag] = field(default_factory=list)
    describe_only: bool = False
    description: Optional[str] = None
    error: Optional[str] = None
    properties: Optional[dict] = None          # [computed], filled by the property module
    similarity_to_parent: Optional[float] = None

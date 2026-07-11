"""Analog generation — the #1 technical risk (PROJECT.md §8), handled with care.

Rules enforced here:
  * Encoded transformations only. Generation is a data-supplied reaction template applied
    at an identified position — no free-form molecule invention.
  * Validate everything. Every product is RDKit-sanitized before it can be returned.
  * Two-way gate. Invalid structures and high-importance-region edits are *flagged*, not
    silently dropped or silently allowed; flags are overridable with the reason recorded.
  * Describe-don't-break. If nothing clean can be generated, return a described,
    position-highlighted analog instead of a broken molecule.

Nothing in this file names a compound, a functional group, or a reaction. Those live in data.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from rdkit import Chem
from rdkit.Chem import AllChem, Mol

from .models import (
    Analog,
    Compound,
    Flag,
    FlagLevel,
    ModifiablePosition,
    Provenance,
    StructureLocator,
    Transformation,
)


def resolve_position(mol: Mol, locator: StructureLocator) -> Optional[int]:
    """Resolve a data-driven locator to a parent atom index. None if it does not match."""
    pattern = Chem.MolFromSmarts(locator.smarts)
    if pattern is None:
        return None
    matches = mol.GetSubstructMatches(pattern)
    if not matches:
        return None
    match = matches[0]
    if not 0 <= locator.target_atom < len(match):  # guard negative / out-of-range (no IndexError)
        return None
    return match[locator.target_atom]


def _reacting_site(product: Mol, mapnum: int) -> Optional[int]:
    """Parent atom index that carried the mapped reacting atom, via RDKit reaction bookkeeping.

    RunReactants tags each product atom that came from the reactant with ``react_atom_idx``
    (its index in the parent) and ``old_mapno`` (its SMARTS atom-map number). That lets us
    attribute a product to the position it was made at.
    """
    for atom in product.GetAtoms():
        if (
            atom.HasProp("old_mapno")
            and atom.GetProp("old_mapno") == str(mapnum)
            and atom.HasProp("react_atom_idx")
        ):
            return int(atom.GetProp("react_atom_idx"))
    return None


def _sanitize(product: Mol) -> tuple[bool, Optional[str], Optional[str]]:
    """Validate a raw reaction product. Returns (ok, canonical_smiles, error)."""
    mol = Chem.Mol(product)
    try:
        Chem.SanitizeMol(mol)
    except Exception as exc:  # RDKit raises several sanitization exception types
        return False, None, str(exc)
    return True, Chem.MolToSmiles(mol), None


def _describe_fallback(
    transformation: Transformation,
    position_label: Optional[str],
    reason: str,
    parent_id: str = "",
    modified_atom_idx: Optional[int] = None,
) -> Analog:
    """Describe-don't-break: describe the edit in words, keeping the parent id and — when the
    site is known — the atom to highlight. Only claims a highlight when there is an atom for it."""
    where = position_label or "the specified position"
    highlight = " Position highlighted for review." if modified_atom_idx is not None else ""
    return Analog(
        parent_id=parent_id,
        transformation_id=transformation.id,
        product_smiles=None,
        valid=False,
        modified_atom_idx=modified_atom_idx,
        describe_only=True,
        description=(
            f"Apply {transformation.name} at {where}. "
            f"Structure not auto-generated ({reason})." + highlight
        ),
        provenance=Provenance.HYPOTHESIS,
        flags=[Flag(code="describe_only", level=FlagLevel.WARNING, message=reason)],
        error=reason,
    )


def apply_transformation(
    mol: Mol,
    transformation: Transformation,
    target_atom_idx: Optional[int] = None,
    position_label: Optional[str] = None,
) -> list[Analog]:
    """Apply one encoded transformation, optionally constrained to one parent atom.

    Returns validated analogs (deduped by canonical SMILES). If nothing valid results,
    returns a single describe-don't-break analog rather than an empty list or a broken mol.
    """
    # ReactionFromSmarts *raises* (not returns None) on the common malformed inputs — a missing
    # '>>', a single-'>' typo, unbalanced parens — so guard the parse, not just a None result.
    # A transformation is hand-authored data; a typo must degrade to describe-don't-break (§8).
    try:
        rxn = AllChem.ReactionFromSmarts(transformation.reaction_smarts)
    except Exception as exc:
        return [_describe_fallback(transformation, position_label, f"invalid reaction SMARTS: {exc}", modified_atom_idx=target_atom_idx)]
    if rxn is None:
        return [_describe_fallback(transformation, position_label, "invalid reaction SMARTS", modified_atom_idx=target_atom_idx)]

    try:
        product_sets = rxn.RunReactants((mol,))
    except Exception as exc:
        return [_describe_fallback(transformation, position_label, f"reaction failed: {exc}", modified_atom_idx=target_atom_idx)]

    parent_smiles = Chem.MolToSmiles(mol)
    analogs: dict[str, Analog] = {}
    first_error: Optional[str] = None
    saw_noop = False
    for product_set in product_sets:
        product = product_set[0]
        site = _reacting_site(product, transformation.reacting_atom_mapnum)
        if target_atom_idx is not None and site != target_atom_idx:
            continue
        ok, smiles, error = _sanitize(product)
        if not ok:
            if first_error is None:
                first_error = error
            continue
        if smiles == parent_smiles:
            saw_noop = True  # sanitizable but unchanged — the edit did not happen; not an analog
            continue
        analogs.setdefault(
            smiles,
            Analog(
                parent_id="",
                transformation_id=transformation.id,
                product_smiles=smiles,
                valid=True,
                modified_atom_idx=site,
                provenance=Provenance.HYPOTHESIS,
            ),
        )

    if not analogs:
        if first_error:
            reason = f"no clean structure could be generated ({first_error})"
        elif saw_noop:
            reason = "transformation produced no change (no-op)"
        else:
            reason = "no clean structure could be generated"
        return [_describe_fallback(transformation, position_label, reason, modified_atom_idx=target_atom_idx)]

    return list(analogs.values())


def importance_gate_flags(compound: Compound, mol: Mol, atom_idx: Optional[int]) -> list[Flag]:
    """Two-way gate (PROJECT.md §6): flag — never forbid — edits to high-importance regions.

    Empty while a compound has no curated importance map (populated Day 3). The mechanism
    is here now so generation and the gate lock together before code accretes.
    """
    if atom_idx is None:
        return []
    flags: list[Flag] = []
    for region in compound.importance_map:
        if region.importance != "high":
            continue
        if resolve_position(mol, region.locator) == atom_idx:
            flags.append(
                Flag(
                    code="high_importance_region",
                    level=FlagLevel.WARNING,
                    message=f"Edits a high-importance region: {region.reason}",
                    overridable=True,
                )
            )
    return flags


def generate_at_position(
    compound: Compound, mol: Mol, transformation: Transformation, position: ModifiablePosition
) -> list[Analog]:
    """End-to-end single-position generation: locate the position from data, apply the
    transformation, validate, and attach parentage plus two-way-gate flags."""
    atom_idx = resolve_position(mol, position.locator)
    if atom_idx is None:
        return [
            _describe_fallback(
                transformation,
                position.label,
                "position could not be located on the structure",
                parent_id=compound.id,
            )
        ]

    gate_flags = importance_gate_flags(compound, mol, atom_idx)
    analogs = apply_transformation(
        mol, transformation, target_atom_idx=atom_idx, position_label=position.label
    )
    for analog in analogs:
        analog.parent_id = compound.id
        # Independent per-analog copies — a shared Flag would let one candidate's override
        # silently mutate another's (the two-way gate's audit meaning must stay candidate-local).
        analog.flags.extend(replace(flag) for flag in gate_flags)
    return analogs

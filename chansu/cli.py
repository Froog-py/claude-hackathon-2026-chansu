"""Minimal Day-1 entry point (PROJECT.md §11's real UI comes later).

    python -m chansu.cli [compound_id]

Loads a compound *from data*, prints its provenance-tagged computed properties, and
generates one validated analog. The engine is compound-agnostic — everything specific to
the demo compound comes from ``data/`` (default compound id lives in ``data/config.json``).
"""

from __future__ import annotations

import sys

from rdkit import Chem

from .core.generation import generate_at_position
from .core.loaders import load_compound, load_config, load_transformation, to_mol
from .core.models import Compound, Provenance, tag
from .core.properties import PropertyProfile, compute_properties, tanimoto_similarity

_COMPUTED = tag(Provenance.COMPUTED)


def _print_header(text: str) -> None:
    print(f"\n{text}")
    print("=" * len(text))


def _print_properties(profile: PropertyProfile) -> None:
    rows = [
        ("Molecular formula", profile.formula),
        ("Molecular weight", f"{profile.mw} g/mol"),
        ("clogP (Crippen)", profile.logp),
        ("TPSA", f"{profile.tpsa} Å²"),
        ("H-bond donors", profile.hbd),
        ("H-bond acceptors", profile.hba),
        ("Rotatable bonds", profile.rotatable_bonds),
        ("Synthetic accessibility", f"{profile.sa_score} (1 easy .. 10 hard)"),
        ("Lipinski Ro5", f"{'pass' if profile.lipinski_pass else 'fail'} ({profile.lipinski_violations} violation(s))"),
        ("Veber", "pass" if profile.veber_pass else "fail"),
    ]
    for label, value in rows:
        print(f"  {label:<26} {value}   {_COMPUTED}")


def run(compound: Compound) -> None:
    mol = to_mol(compound)

    _print_header(f"Compound: {compound.name}  ({compound.id})")
    src_parts = [p for p in (compound.source, compound.source_id) if p]
    src = " ".join(src_parts) if src_parts else "(unsourced)"
    # A database record (e.g. a PubChem CID) is verifiable provenance for the structure, but
    # it is not a literature citation — do not tag it [literature — cited] (PROJECT.md §6).
    print(f"  Structure source : {src}   (database record)")
    print(f"  InChIKey         : {compound.inchikey or '(n/a)'}")
    print(f"  Canonical SMILES : {compound.smiles}")
    if compound.annotations.get("class"):
        print(f"  Class (annotation): {compound.annotations['class']}")

    _print_header("Computed properties")
    profile = compute_properties(mol)
    _print_properties(profile)

    _print_header("Generation spike — one encoded transformation at one position")
    if not compound.modifiable_positions:
        print("  No modifiable positions defined in data; nothing to generate.")
        return

    position = compound.modifiable_positions[0]
    # Day-1 default transformation lives in data; the engine does not name it.
    transformation_id = load_config().get("demo_transformation")
    if not transformation_id:
        print("  No demo_transformation configured in data/config.json; skipping generation.")
        return
    transformation = load_transformation(transformation_id)
    print(f"  Transformation : {transformation.name}   [{transformation.id}]")
    print(f"  Position       : {position.label}   [{position.id}]")

    analogs = generate_at_position(compound, mol, transformation, position)
    for analog in analogs:
        if analog.describe_only:
            print(f"\n  [describe-only fallback] {analog.description}")
            continue
        analog_mol = Chem.MolFromSmiles(analog.product_smiles)
        analog.properties = compute_properties(analog_mol).as_dict()
        analog.similarity_to_parent = round(tanimoto_similarity(mol, analog_mol), 3)

        print(f"\n  Analog: {analog.product_smiles}")
        print(f"    valid            : {analog.valid}   {tag(analog.provenance)}")
        print(f"    modified atom    : {analog.modified_atom_idx}")
        print(f"    formula / MW     : {analog.properties['formula']}  /  {analog.properties['mw']} g/mol   [computed]")
        print(f"    similarity-parent: {analog.similarity_to_parent} (Tanimoto, ECFP4)   [computed]")
        if analog.flags:
            for flag in analog.flags:
                print(f"    flag [{flag.level.value}]: {flag.message}")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    compound_id = argv[0] if argv else load_config().get("demo_compound")
    if not compound_id:
        print("No compound id given and no demo_compound in data/config.json", file=sys.stderr)
        return 2
    run(load_compound(compound_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

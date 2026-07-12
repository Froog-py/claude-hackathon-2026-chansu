"""Entry point / demo (PROJECT.md §11's real Streamlit UI is Day 5).

    python -m chansu.cli [compound_id]

Loads a compound *from data* and prints the full provenance-tagged design memo: grounded
targets / liabilities / importance map, gated and scored candidate analogs, and honest
failure where nothing applies. The engine is compound-agnostic — everything specific to the
demo compound comes from ``data/`` (default compound id lives in ``data/config.json``).
"""

from __future__ import annotations

import sys

from .core.loaders import load_compound, load_config, load_strategies, to_mol
from .core.models import Compound, Provenance, tag
from .core.properties import PropertyProfile, compute_properties
from .report import render_memo

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
    # The full design memo: grounding + gated, scored candidate analogs + honest failure.
    print(render_memo(compound, mol, load_strategies()))
    _print_header("Parent computed properties")
    _print_properties(compute_properties(mol))


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

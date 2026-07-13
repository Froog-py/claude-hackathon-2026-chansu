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
from .core.pipeline import design
from .core.properties import PropertyProfile, compute_properties
from .reasoning.adapter import ClaudeReasoningModel
from .reasoning.design_reasoning import reason_over_design
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


def run(compound: Compound, depth: str = "strategy") -> None:
    mol = to_mol(compound)
    # Deterministic design (RDKit + strategy library), then the reasoning model's runtime analysis
    # through the adapter interface. Claude is the backend today; swapping models is a change here,
    # not in the pipeline. ``depth`` selects strategy-level (default, safe) or compound-specific
    # (opt-in, falls back to strategy-level on refusal). If no backend is configured, reason_over_design
    # degrades and the memo falls back to the deterministic design with an honest note.
    result = design(compound, mol, load_strategies())
    # Medium effort: short analogical explanations, not deep multi-step problems (the documented
    # sweet spot; keeps adaptive thinking within the token budget).
    reasoning = reason_over_design(compound, result, ClaudeReasoningModel(effort="medium"), depth=depth)
    print(render_memo(compound, mol, result, reasoning))
    _print_header("Parent computed properties")
    _print_properties(compute_properties(mol))


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    # Minimal parse: [compound_id] [--depth strategy|compound]
    depth = "strategy"
    positional: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--depth":
            depth = argv[i + 1] if i + 1 < len(argv) else None  # trailing --depth: fails the check below
            i += 2
        else:
            positional.append(argv[i])
            i += 1
    if depth not in ("strategy", "compound"):
        print(f"--depth must be 'strategy' or 'compound', got {depth!r}", file=sys.stderr)
        return 2
    compound_id = positional[0] if positional else load_config().get("demo_compound")
    if not compound_id:
        print("No compound id given and no demo_compound in data/config.json", file=sys.stderr)
        return 2
    run(load_compound(compound_id), depth=depth)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

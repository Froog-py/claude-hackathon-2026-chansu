"""Day-1 core tests: the two spikes made executable (BUILD_PLAN.md).

  * generic-engine rule (PROJECT.md §5) — the acceptance test, as code
  * bufalin loads from data with the right identity
  * deterministic properties are sane
  * the generation spike yields a valid, sanitizable structure
"""

import ast
import json
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from chansu.core.generation import apply_transformation, generate_at_position
from chansu.core.loaders import load_compound, load_transformation, to_mol
from chansu.core.models import Transformation
from chansu.core.properties import compute_properties, tanimoto_similarity

ENGINE_DIR = Path(__file__).resolve().parents[1] / "chansu"

# Compound-specific chemistry that must never appear in engine code (PROJECT.md §5).
FORBIDDEN_TOKENS = [
    "bufalin",
    "bufadienolide",
    "cardiac glycoside",
    "atpase",
    "na+/k+",
    "steroid",
    "pyranone",
    "lactone",
    "acetyl",
    "acetate",
]

def _inlined_chemistry(path):
    """Engine leaks a name-grep misses: hard-coded chemistry (an acetyl group is 'C(C)=O' — no
    forbidden name). Uses the AST so comments/prose can't false-positive. Flags (a) a reaction
    arrow '>>' inside a non-docstring string literal, and (b) a string literal passed straight
    into a SMARTS/SMILES parser. Engine code must pass structure through as data (variables)."""
    tree = ast.parse(path.read_text())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            first = body[0].value if body and isinstance(body[0], ast.Expr) else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                docstrings.add(id(first))
    offenders = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and ">>" in node.value
        ):
            offenders.append(f"inlined reaction SMARTS literal {node.value!r}")
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if (
                name.endswith(("FromSmarts", "FromSmiles"))
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                offenders.append(f"inlined chemistry: {name}(<string literal>)")
    return offenders


def test_generic_engine_rule_no_compound_knowledge_in_engine():
    offenders = []
    for path in ENGINE_DIR.rglob("*.py"):
        rel = path.relative_to(ENGINE_DIR)
        lowered = path.read_text().lower()
        for token in FORBIDDEN_TOKENS:
            if token in lowered:
                offenders.append(f"{rel}: name token {token!r}")
        offenders += [f"{rel}: {msg}" for msg in _inlined_chemistry(path)]
    assert not offenders, "compound-specific knowledge leaked into the engine:\n" + "\n".join(offenders)


def test_bufalin_loads_from_data_with_expected_identity():
    compound = load_compound("bufalin")
    mol = to_mol(compound)
    assert compound.source == "PubChem"
    assert compound.source_id == "CID 9547215"
    assert compound.inchikey == "QEEBRPGZBVVINN-BMPKRDENSA-N"
    assert rdMolDescriptors.CalcMolFormula(mol) == "C24H34O4"


def test_bufalin_properties_are_sane():
    profile = compute_properties(to_mol(load_compound("bufalin")))
    assert 386.0 < profile.mw < 387.0
    assert profile.hbd == 2
    assert profile.hba == 4
    assert profile.rotatable_bonds == 1
    assert profile.lipinski_pass and profile.veber_pass  # real liabilities are elsewhere


def test_generation_spike_produces_valid_structure():
    compound = load_compound("bufalin")
    mol = to_mol(compound)
    transformation = load_transformation("o_acetylation")
    position = compound.modifiable_positions[0]  # C3-OH

    analogs = generate_at_position(compound, mol, transformation, position)
    valid = [a for a in analogs if a.valid and a.product_smiles]
    assert valid, "generation spike produced no valid structure"

    analog = valid[0]
    analog_mol = Chem.MolFromSmiles(analog.product_smiles)
    assert analog_mol is not None, "valid analog SMILES did not re-parse"
    assert rdMolDescriptors.CalcMolFormula(analog_mol) == "C26H36O5"  # + one acetyl
    assert tanimoto_similarity(mol, analog_mol) > 0.5  # active core intact
    assert analog.parent_id == "bufalin"


def test_unlocatable_position_falls_back_to_describe_not_break():
    from chansu.core.models import ModifiablePosition, StructureLocator

    compound = load_compound("bufalin")
    mol = to_mol(compound)
    transformation = load_transformation("o_acetylation")
    # A locator that cannot match -> engine must describe, never crash or emit garbage.
    impossible = ModifiablePosition(
        id="nope", label="nonexistent site", locator=StructureLocator(smarts="[Xe]")
    )
    analogs = generate_at_position(compound, mol, transformation, impossible)
    assert len(analogs) == 1 and analogs[0].describe_only and not analogs[0].valid


def test_generic_engine_accepts_a_new_compound_with_data_only(tmp_path):
    """The §5 acceptance test, positively demonstrated: a structurally unlike compound
    (cyclohexanol — a simple aliphatic alcohol, nothing like the steroid flagship) loads and
    generates through the SAME engine with only a new data file and ZERO engine edits."""
    data_dir = tmp_path / "data"
    (data_dir / "compounds").mkdir(parents=True)
    (data_dir / "compounds" / "fixture.json").write_text(
        json.dumps(
            {
                "id": "fixture",
                "name": "Cyclohexanol",
                "structure": {"smiles": "OC1CCCCC1", "source": "test", "source_id": "n/a"},
                "modifiable_positions": [
                    {
                        "id": "oh",
                        "label": "secondary hydroxyl",
                        "locator": {"smarts": "[CH1][OX2H1]", "target_atom": 1},
                    }
                ],
            }
        )
    )
    compound = load_compound("fixture", override=data_dir)
    mol = to_mol(compound)
    assert compute_properties(mol).formula == "C6H12O"

    transformation = load_transformation("o_acetylation")  # reused unchanged from repo data
    analogs = generate_at_position(compound, mol, transformation, compound.modifiable_positions[0])
    valid = [a for a in analogs if a.valid and a.product_smiles]
    assert valid, "engine failed to generate on a data-only new compound"
    product = Chem.MolFromSmiles(valid[0].product_smiles)
    assert rdMolDescriptors.CalcMolFormula(product) == "C8H14O2"  # cyclohexyl acetate


def test_malformed_reaction_smarts_falls_back_not_crash():
    """A SMARTS typo in hand-authored transformation data must degrade to describe-don't-break,
    not raise out of the public API (PROJECT.md §8)."""
    compound = load_compound("bufalin")
    mol = to_mol(compound)
    bad = Transformation(
        id="bad", name="typo", reaction_smarts="[C:1][OX2H1:2]>[C:1]O", reacting_atom_mapnum=2
    )  # single '>' instead of '>>'
    analogs = apply_transformation(mol, bad)
    assert len(analogs) == 1 and analogs[0].describe_only and not analogs[0].valid

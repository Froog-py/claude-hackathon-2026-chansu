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
    # the reported site must be the requested C3-OH atom — a right-formula edit at the wrong
    # site would otherwise pass unnoticed
    from chansu.core.generation import resolve_position

    assert analog.modified_atom_idx == resolve_position(mol, position.locator)


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


def test_no_op_reaction_is_not_accepted_as_an_analog():
    """A sanitizable product identical to the parent means the edit did not happen — it must
    not be emitted as a valid analog (Codex P1: identity reaction was accepted)."""
    compound = load_compound("bufalin")
    mol = to_mol(compound)
    identity = Transformation(id="id", name="identity", reaction_smarts="[C:1]>>[C:1]", reacting_atom_mapnum=1)
    analogs = apply_transformation(mol, identity)
    assert not [a for a in analogs if a.valid], "a no-op reaction was accepted as a valid analog"
    assert analogs[0].describe_only and "no-op" in (analogs[0].error or "")


def test_gate_override_is_candidate_local():
    """Overriding one candidate's flag must not mutate another's (Codex P1: shared Flag objects)."""
    from chansu.core.models import ImportanceRegion, StructureLocator

    compound = load_compound("bufalin")
    mol = to_mol(compound)
    # Flag the C3 site high-importance and generate two candidates at it via two transformations.
    compound.importance_map = [
        ImportanceRegion(
            id="r",
            locator=StructureLocator(smarts="[CH1][OX2H1]", target_atom=1),
            importance="high",
            reason="test region",
        )
    ]
    pos = compound.modifiable_positions[0]
    a = generate_at_position(compound, mol, load_transformation("o_acetylation"), pos)[0]
    b = generate_at_position(compound, mol, load_transformation("o_acetylation"), pos)[0]
    a_flag = next(f for f in a.flags if f.code == "high_importance_region")
    b_flag = next(f for f in b.flags if f.code == "high_importance_region")
    assert a_flag is not b_flag  # independent objects
    a_flag.override("intended edit")
    assert not b_flag.overridden and b_flag.override_reason is None


def test_negative_locator_index_does_not_crash():
    """A negative target_atom must be rejected at load, and resolve must not raise (Codex P1)."""
    import pytest

    from chansu.core.loaders import _locator
    from chansu.core.generation import resolve_position
    from chansu.core.models import StructureLocator

    with pytest.raises(ValueError):
        _locator({"smarts": "[CH1][OX2H1]", "target_atom": -99})
    mol = to_mol(load_compound("bufalin"))
    assert resolve_position(mol, StructureLocator(smarts="[CH1][OX2H1]", target_atom=-99)) is None


def test_unlocatable_fallback_keeps_parent_id_and_no_false_highlight():
    """The describe-only fallback for an unlocatable site must carry the parent id and must not
    claim a highlight it cannot provide (Codex P1)."""
    from chansu.core.models import ModifiablePosition, StructureLocator

    compound = load_compound("bufalin")
    mol = to_mol(compound)
    impossible = ModifiablePosition(id="nope", label="nonexistent", locator=StructureLocator(smarts="[Xe]"))
    analog = generate_at_position(compound, mol, load_transformation("o_acetylation"), impossible)[0]
    assert analog.parent_id == "bufalin"
    assert analog.modified_atom_idx is None
    assert "highlighted" not in (analog.description or "")


def test_blank_override_reason_is_rejected():
    from chansu.core.models import Flag, FlagLevel
    import pytest

    flag = Flag(code="c", level=FlagLevel.WARNING, message="m")
    for blank in ("", "   ", "\n"):
        with pytest.raises(ValueError):
            flag.override(blank)
    assert not flag.overridden


def test_strategy_library_loads_all_entries_with_verified_citations():
    """The precedent-backed library: every entry has a precedent + citation, is keyed on
    liability class + attachment type (compound-agnostic), and any declared transformation
    actually resolves (PROJECT.md §6, §7)."""
    from chansu.core.loaders import load_strategies, load_transformation

    library = load_strategies()
    ids = {s.id for s in library}
    assert {
        "soft_drug_self_inactivation",
        "glycosylation_isoform_selectivity",
        "tumor_activated_prodrug_enzyme",
        "tumor_activated_prodrug_hypoxia",
        "targeting_ligand_conjugation",
        "ester_prodrug_pk_masking",
    } <= ids

    for s in library:
        assert s.precedent_drug, f"{s.id} has no precedent drug"
        assert s.citation and s.citation.label and s.citation.source, f"{s.id} missing a citation"
        assert s.liability_classes and s.attachment_types, f"{s.id} not keyed on class + type"
        if s.transformation_id:  # a declared transformation must actually exist
            assert load_transformation(s.transformation_id).id == s.transformation_id


def test_uncited_strategy_is_rejected():
    import pytest

    from chansu.core.loaders import strategy_from_dict

    with pytest.raises(ValueError):
        strategy_from_dict(
            {"id": "x", "concept": "c", "mechanism": "m", "precedent_drug": "d", "citation": None}
        )


def test_ester_prodrug_transformation_fires_on_acid_not_on_bufalin():
    """The ester-prodrug strategy's encoded transformation makes a valid ester on a carboxyl
    compound, and honestly declines on bufalin (no carboxyl) -> describe-and-highlight."""
    from chansu.core.generation import apply_transformation, generate_at_position
    from chansu.core.loaders import load_transformation
    from chansu.core.models import ModifiablePosition, StructureLocator

    t = load_transformation("carboxyl_to_ethyl_ester")

    acid = Chem.MolFromSmiles("CC(C)Cc1ccc(C(C)C(=O)O)cc1")  # ibuprofen (has -COOH)
    valid = [a for a in apply_transformation(acid, t) if a.valid and a.product_smiles]
    assert valid, "ester-prodrug transformation did not fire on a carboxylic acid"
    assert rdMolDescriptors.CalcMolFormula(Chem.MolFromSmiles(valid[0].product_smiles)) == "C15H22O2"

    compound = load_compound("bufalin")
    mol = to_mol(compound)
    cooh = ModifiablePosition(
        id="cooh", label="carboxyl", locator=StructureLocator(smarts="[CX3](=O)[OX2H1]")
    )
    analogs = generate_at_position(compound, mol, t, cooh)
    assert len(analogs) == 1 and analogs[0].describe_only and not analogs[0].valid


def test_match_strategies_grounds_and_declines_honestly():
    """Liabilities match precedent strategies by class; matches are actionable only where the
    attachment point exists; a liability with no strategy is honest failure (PROJECT.md §6)."""
    from chansu.core.loaders import load_compound, load_strategies
    from chansu.core.matching import match_strategies

    compound = load_compound("bufalin")
    matches = match_strategies(compound, load_strategies())

    for m in matches:  # every matched strategy is precedent-backed (cited)
        if m.strategy is not None:
            assert m.strategy.citation and m.strategy.citation.source

    by_liab: dict = {}
    for m in matches:
        by_liab.setdefault(m.liability.kind, []).append(m)

    # systemic toxicity -> soft-drug, actionable (bufalin has hydroxyl handles + a transformation)
    soft = [m for m in by_liab["systemic_toxicity"] if m.strategy and m.strategy.id == "soft_drug_self_inactivation"]
    assert soft and soft[0].actionable and soft[0].strategy.transformation_id

    # poor solubility -> ester-prodrug matched by class but NOT actionable (bufalin has no -COOH)
    ester = [m for m in by_liab["poor_solubility"] if m.strategy and m.strategy.id == "ester_prodrug_pk_masking"]
    assert ester and not ester[0].actionable

    # rapid clearance -> no precedented strategy at all (the tool declines, does not invent one)
    assert any(m.strategy is None for m in by_liab["rapid_clearance"])


def test_grounding_report_is_cited_and_declines_to_overclaim():
    from chansu.core.loaders import load_compound, load_strategies
    from chansu.report import render_grounding

    text = render_grounding(load_compound("bufalin"), load_strategies())
    assert "[literature · cited]" in text
    assert "PMID 20388710" in text  # Katz 2010 (NCBI-verified) is surfaced
    assert "no strategy in the current curated library" in text  # bounded honest failure
    assert "formulation-delivery" not in text  # invents no out-of-scope route
    assert "no site fabricated" in text  # attachment-point honesty


def test_uncited_claim_is_never_tagged_as_literature_cited():
    """A programmatic compound with uncited roles must render as uncited, never a false
    [literature · cited] (Codex P1: the renderer never emits a cited tag it can't back)."""
    from chansu.core.models import Compound, Liability, Target
    from chansu.report import render_grounding

    compound = Compound(
        id="x",
        name="X",
        smiles="CCO",
        targets=[Target(name="SomeTarget", role="role")],
        liabilities=[Liability(kind="poor_solubility", detail="detail")],
    )
    text = render_grounding(compound, [])
    assert "[uncited · not literature-backed]" in text
    assert "[literature · cited]" not in text  # nothing here is cited, so nothing claims it


def test_duplicate_liability_kind_is_rejected_at_load():
    """kind is the grouping key for candidates; duplicates would silently merge two liabilities
    (Codex P3)."""
    import pytest

    from chansu.core.loaders import compound_from_dict

    with pytest.raises(ValueError):
        compound_from_dict(
            {
                "id": "dup",
                "name": "Dup",
                "structure": {"smiles": "CCO"},
                "liabilities": [
                    {"kind": "poor_solubility", "detail": "a"},
                    {"kind": "poor_solubility", "detail": "b"},
                ],
            }
        )


def test_strategy_transform_attachment_mismatch_is_rejected_at_load():
    """A strategy declaring a transformation it is attachment-incompatible with is inconsistent
    library data — reject it before matching can call it actionable (Codex P2)."""
    import pytest

    from chansu.core.loaders import _check_transformation_compat
    from chansu.core.models import Citation, Strategy

    bad = Strategy(
        id="x",
        concept="c",
        mechanism="m",
        precedent_drug="d",
        citation=Citation(label="l", source="s"),
        attachment_types=["amine"],           # o_acetylation applies only to hydroxyls
        transformation_id="o_acetylation",
    )
    with pytest.raises(ValueError):
        _check_transformation_compat(bad, None)

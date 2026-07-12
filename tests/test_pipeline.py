"""Day-4 tests: the full loop — generate across strategies, gate, score, memo (BUILD_PLAN.md).

The must-ship, made executable: feeding bufalin yields valid ranked candidates whose scores are
transparent, whose high-importance edits are flagged (not blocked), and whose memo declines to
over-claim where nothing applies.
"""

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from chansu.core.loaders import load_compound, load_strategies, to_mol
from chansu.core.pipeline import design, ranked_valid
from chansu.core.scoring import DEFAULT_WEIGHTS, score
from chansu.report import render_memo


def test_design_loop_generates_gates_and_scores():
    compound = load_compound("bufalin")
    mol = to_mol(compound)
    result = design(compound, mol, load_strategies())

    valid = ranked_valid(result)
    assert valid, "no valid candidate generated"
    # ranked by score, descending
    assert all(valid[i].score.total >= valid[i + 1].score.total for i in range(len(valid) - 1))

    # the soft-drug strategy generates at both hydroxyl handles; exactly the C14 edit trips the
    # two-way gate (essential C14-OH), the C3 edit does not.
    soft = [c for c in valid if c.strategy.id == "soft_drug_self_inactivation"]
    assert len(soft) == 2
    flagged = [c for c in soft if any(f.code == "high_importance_region" for f in c.flags)]
    unflagged = [c for c in soft if not c.flags]
    assert len(flagged) == 1 and len(unflagged) == 1  # gate fires on exactly one

    # every valid candidate is a re-parseable structure with a computed property profile
    for c in valid:
        assert Chem.MolFromSmiles(c.analog.product_smiles) is not None
        assert c.properties and c.properties["formula"]

    # honest failure: rapid_clearance has no precedented strategy
    assert any(lib.kind == "rapid_clearance" for lib in result.unaddressed)


def test_score_is_transparent_and_bounded():
    mol = to_mol(load_compound("bufalin"))
    analog = Chem.MolFromSmiles("CC(=O)O[C@H]1CC[C@@]2(C)[C@H](CC[C@@H]3[C@@H]2CC[C@]2(C)[C@@H](c4ccc(=O)oc4)CC[C@]32O)C1")
    s = score(mol, analog)
    for component in (s.similarity, s.ease, s.druglikeness, s.total):
        assert 0.0 <= component <= 1.0
    expected = (
        s.weights["similarity"] * s.similarity
        + s.weights["ease"] * s.ease
        + s.weights["druglikeness"] * s.druglikeness
    )
    assert abs(s.total - round(expected, 3)) < 0.02  # total is the shown weighted sum
    assert s.weights == DEFAULT_WEIGHTS


def test_memo_is_the_tagged_must_ship_deliverable():
    compound = load_compound("bufalin")
    memo = render_memo(compound, to_mol(compound), load_strategies())

    assert "DESIGN MEMO" in memo
    assert "score =" in memo and "similarity-to-parent" in memo  # transparent rubric shown
    assert "[hypothesis — needs wet-lab validation]" in memo      # candidates tagged as hypotheses
    assert "[literature — cited]" in memo and "PMID 20388710" in memo  # cited grounding
    assert "FLAG [warning]" in memo and "high-importance" in memo.lower()  # two-way gate visible
    assert "overridable" in memo                                   # gate allows override
    assert "no well-precedented strategy applies" in memo          # honest failure (rapid_clearance)
    assert "predicts binding, toxicity, or efficacy" in memo       # non-goals restated

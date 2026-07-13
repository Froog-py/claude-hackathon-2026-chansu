"""Tests for the pure-Python prompt builder (chansu/ingest_prompts.py)."""
from chansu import ingest_prompts as p


def test_project_setup_names_the_trust_boundary():
    setup = p.build_project_setup()
    assert p.PROJECT_NAME in setup
    low = setup.lower()
    assert "pubmed" in low and "fabricate" in low  # citation discipline is stated


def test_review_prompt_injects_name_schema_and_vocabulary():
    prompt = p.build_review_prompt("Curcumin", vocabulary=({"hydroxyl", "carboxyl"}, {"poor_solubility"}))
    assert "Curcumin" in prompt
    assert "smiles" in prompt.lower()   # schema is embedded
    assert "hydroxyl" in prompt          # vocabulary is embedded
    assert "poor_solubility" in prompt


def test_review_prompt_optional_liability_focus():
    prompt = p.build_review_prompt("Curcumin", vocabulary=(set(), set()), liability_focus="rapid_clearance")
    assert "rapid_clearance" in prompt

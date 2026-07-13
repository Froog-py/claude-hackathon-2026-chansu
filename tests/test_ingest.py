"""Tests for the deterministic ingest gate (chansu/ingest.py). Pure Python; a small aspirin record
stands in for any compound — the gate is generic (§5)."""
from rdkit import Chem

from chansu import ingest
from chansu.core.loaders import load_compound, load_strategies

# A minimal valid record (aspirin) — generic fixture, no bearing on the flagship.
_VALID = {
    "id": "demo_compound",
    "name": "Demo compound",
    "structure": {"smiles": "CC(=O)Oc1ccccc1C(=O)O", "source": "PubChem", "source_id": "CID 2244"},
    "liabilities": [
        {"kind": "poor_solubility", "detail": "x", "citation": {"label": "A 2020", "source": "PMID 12345678"}}
    ],
}


def _levels(report, subject):
    return {c.level for c in report.checks if c.subject == subject}


# --- Task 1: report types + vocabulary -------------------------------------------------------

def test_derive_vocabulary_unions_the_library():
    attach, liab = ingest.derive_vocabulary(load_strategies())
    assert attach and liab
    assert all(isinstance(x, str) for x in attach | liab)


def test_report_partitions_checks_by_level():
    checks = [ingest.Check("fail", "a"), ingest.Check("flag", "b"), ingest.Check("pass", "c")]
    report = ingest.IngestReport(ok=False, record={}, checks=checks)
    assert [c.message for c in report.fails] == ["a"]
    assert [c.message for c in report.flags] == ["b"]


# --- Task 2: structural hard-fails -----------------------------------------------------------

def test_valid_record_has_no_hard_fail_and_canonicalizes():
    report = ingest.validate_record(_VALID, load_strategies())
    assert report.ok
    assert not report.fails
    out = report.record["structure"]["smiles"]
    assert Chem.MolFromSmiles(out) is not None
    assert out == Chem.MolToSmiles(Chem.MolFromSmiles(_VALID["structure"]["smiles"]))


def test_invalid_smiles_hard_fails():
    bad = {**_VALID, "structure": {"smiles": "not_a_molecule)("}}
    report = ingest.validate_record(bad, load_strategies())
    assert not report.ok
    assert "fail" in _levels(report, "structure.smiles")


def test_missing_required_field_hard_fails():
    bad = {k: v for k, v in _VALID.items() if k != "name"}
    report = ingest.validate_record(bad, load_strategies())
    assert not report.ok
    assert any(c.level == "fail" and c.subject == "name" for c in report.checks)


def test_invalid_locator_smarts_hard_fails():
    bad = {**_VALID, "importance_map": [
        {"id": "r1", "importance": "high", "reason": "x", "locator": {"smarts": "[[bad"}}
    ]}
    report = ingest.validate_record(bad, load_strategies())
    assert not report.ok
    assert any(c.level == "fail" and c.subject == "importance_map" for c in report.checks)


def test_duplicate_liability_kind_hard_fails():
    bad = {**_VALID, "liabilities": [
        {"kind": "poor_solubility", "citation": {"label": "A", "source": "PMID 1"}},
        {"kind": "poor_solubility", "citation": {"label": "B", "source": "PMID 2"}},
    ]}
    report = ingest.validate_record(bad, load_strategies())
    assert not report.ok
    assert any(c.level == "fail" and c.subject == "liabilities" for c in report.checks)


def test_id_collision_flags_not_fails():
    report = ingest.validate_record(_VALID, load_strategies(), existing_ids={"demo_compound"})
    assert report.ok  # a flag does not block
    assert any(c.level == "flag" and c.subject == "id" for c in report.checks)


def test_unsafe_id_hard_fails():
    # path traversal / bad filename chars must be rejected before write_record builds a path
    for bad in ["../etc/passwd", "a/b", "has space", "UPPER", "trailing.dot"]:
        report = ingest.validate_record({**_VALID, "id": bad}, load_strategies())
        assert not report.ok, f"{bad!r} should be rejected"
        assert any(c.level == "fail" and c.subject == "id" for c in report.checks)


# --- Task 3: advisory soft-flags -------------------------------------------------------------

def test_unresolvable_locator_flags():
    # a valid SMARTS that matches nothing on aspirin (a phosphorus atom)
    rec = {**_VALID, "importance_map": [
        {"id": "r1", "importance": "high", "reason": "x", "locator": {"smarts": "[P]", "label": "phantom"}}
    ]}
    report = ingest.validate_record(rec, load_strategies())
    assert report.ok  # advisory, not blocking
    assert any(c.level == "flag" and "matches no site" in c.message for c in report.checks)


def test_offvocab_liability_flags():
    rec = {**_VALID, "liabilities": [
        {"kind": "definitely_not_a_library_class", "citation": {"label": "A", "source": "PMID 1"}}
    ]}
    report = ingest.validate_record(rec, load_strategies())
    assert any(c.level == "flag" and c.subject == "liabilities" for c in report.checks)


def test_uncited_claim_flags():
    rec = {**_VALID, "targets": [{"name": "SomeTarget"}]}  # no citation
    report = ingest.validate_record(rec, load_strategies())
    assert any(c.level == "flag" and c.subject == "targets" for c in report.checks)


def test_cited_claim_gets_a_link_not_a_flag():
    rec = {**_VALID, "targets": [
        {"name": "SomeTarget", "citation": {"label": "A 2020", "source": "PMID 20388710"}}
    ]}
    report = ingest.validate_record(rec, load_strategies())
    target_checks = [c for c in report.checks if c.subject == "targets"]
    assert target_checks and all(c.level != "flag" for c in target_checks)
    assert any(c.link and "pubmed" in c.link for c in target_checks)


# --- Task 4: write path ----------------------------------------------------------------------

def test_write_record_round_trips(tmp_path):
    (tmp_path / "compounds").mkdir()
    report = ingest.validate_record(_VALID, load_strategies())
    path = ingest.write_record(report, source="claude-science-import", override=tmp_path)
    assert path.exists()
    loaded = load_compound("demo_compound", override=tmp_path)
    assert loaded.name == "Demo compound"
    assert loaded.annotations.get("source") == "claude-science-import"


def test_write_record_refuses_a_failing_record(tmp_path):
    report = ingest.validate_record({**_VALID, "structure": {"smiles": "x)("}}, load_strategies())
    try:
        ingest.write_record(report, override=tmp_path)
        assert False, "should have refused a failing record"
    except ValueError:
        pass

"""The Reference workspace index (PROJECT.md §9): aggregate existing citations into a deduped, groupable
list, with no new data authoring and no fabrication."""

from chansu.core.loaders import load_compound, load_strategies
from chansu.core.models import Citation, Compound, Target
from chansu.references import build_reference_index


def _index():
    compound = load_compound("bufalin")
    return compound, build_reference_index(compound, load_strategies())


def test_index_dedupes_papers_shared_across_claims():
    """A paper cited by several claims collapses to one Reference, so the index has fewer entries than the
    total number of citing claims."""
    compound, refs = _index()
    total_claims = (
        sum(1 for t in compound.targets if t.citation)
        + sum(1 for l in compound.liabilities if l.citation)
        + sum(1 for r in compound.importance_map if r.citation)
        + len(load_strategies())
    )
    assert refs
    assert len(refs) < total_claims  # dedupe actually happened
    assert len({r.key for r in refs}) == len(refs)  # keys are unique


def test_shared_paper_aggregates_its_roles_and_backs():
    """Katz 2010 (PMID 20388710) backs several bufalin claims across roles — it must aggregate into one
    Reference recording every claim it backs, with derived PubMed + DOI links."""
    _, refs = _index()
    katz = next((r for r in refs if r.pmid == "20388710"), None)
    assert katz is not None, "expected the repeated Katz 2010 citation in the index"
    assert len(katz.backs) >= 2                       # cited by more than one claim
    assert len(katz.roles) >= 1
    assert any("pubmed.ncbi.nlm.nih.gov/20388710" in u for u in katz.urls)
    assert any("doi.org/10.1074/jbc.M110.119248" in u for u in katz.urls)
    assert katz.citation and "Katz" in katz.citation


def test_strategy_precedents_are_indexed_with_their_role():
    _, refs = _index()
    strat_refs = [r for r in refs if "strategy-precedent" in r.roles]
    assert strat_refs, "strategy precedents must appear in the reference workspace"
    # every strategy precedent traces to a real paper (label present)
    assert all(r.citation for r in strat_refs)


def test_notes_are_aggregated_across_every_citing_claim_not_just_the_first():
    """A note carried by a *later* claim citing a paper must still reach the Reference — notes are the
    extract-once/reuse-many provenance trail (§9). On bufalin, the Katz 2010 paper is first cited by a
    claim with no note and later by the glycosylation strategy whose citation carries a substantive note;
    that note must not be dropped."""
    _, refs = _index()
    katz = next((r for r in refs if r.pmid == "20388710"), None)
    assert katz is not None
    assert katz.notes, "the note attached to a later citation of Katz 2010 must be aggregated, not dropped"
    assert any("sugar" in n.lower() or "selectiv" in n.lower() for n in katz.notes)


def test_dedupe_merges_a_paper_cited_with_different_identifier_subsets():
    """A paper cited once with a full 'PMID | DOI' source and once with only the PMID must collapse to a
    single Reference (dedupe by any shared identifier) — heterogeneous citations from an external source
    must not split one paper into two entries."""
    compound = Compound(
        id="synthetic", name="Synthetic", smiles="CCO",
        targets=[
            Target(name="T-full", citation=Citation(label="Doe J 2020. Some paper.", source="PMID 12345 | DOI 10.1000/xyz")),
            Target(name="T-pmid-only", citation=Citation(label="Doe J 2020. Some paper.", source="PMID 12345")),
        ],
    )
    refs = build_reference_index(compound, [])
    assert len(refs) == 1  # one paper, not two
    ref = refs[0]
    assert ref.pmid == "12345" and ref.doi == "10.1000/xyz"  # doi back-filled / retained
    assert {s for s in ref.subjects} == {"T-full", "T-pmid-only"}
    assert any("pubmed.ncbi.nlm.nih.gov/12345" in u for u in ref.urls)


def test_references_invents_nothing_for_uncited_claims():
    """A claim with no citation contributes no reference — the index never fabricates a source (§6)."""
    compound = load_compound("bufalin")
    # a compound with its citations stripped yields no references from the compound side
    for t in compound.targets:
        t.citation = None
    for l in compound.liabilities:
        l.citation = None
    for r in compound.importance_map:
        r.citation = None
    refs = build_reference_index(compound, [])
    assert refs == []

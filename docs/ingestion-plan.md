# Compound Ingestion (Path A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a chemist bring a new compound into Chansu from a Claude Science literature review through a pure-Python validation gate, with no engine change (adding a compound stays data-only).

**Architecture:** A framework-agnostic ingest module (`chansu/ingest.py`) validates an externally-authored compound record and returns a transparent `IngestReport` (never raises past the boundary); a pure-Python prompt builder (`chansu/ingest_prompts.py`) emits the Claude Science project setup + per-compound prompt; a Streamlit "Add compound" tab (`chansu/ui/ingest.py`) drives builder → paste → gate → write. Writing lands `data/compounds/<id>.json`, which the existing selector auto-discovers.

**Tech Stack:** Python 3.12, RDKit (structure validation only), Streamlit (UI). No model calls anywhere in this plan.

## Global Constraints

- **Python 3.12 in `.venv`.** Test with `.venv/bin/python -m pytest -q`. Run app with `.venv/bin/streamlit run chansu/ui/app.py`.
- **Generic engine (PROJECT.md §5).** No compound-specific tokens anywhere in `chansu/` *including comments and string constants* (banned: bufalin, bufadienolide, cardiac glycoside, atpase, na+/k+, steroid, pyranone, lactone, acetyl, acetate). `tests/test_core.py::test_generic_engine_rule` must stay green. The prompt text and gate are generic; vocabulary is derived from data at runtime, never hardcoded.
- **Trust boundary (PROJECT.md §6).** The gate never fabricates or auto-verifies a citation. An unverifiable citation stays flagged uncited. Honest-failure / decline states render in the calm `.cs-declined` register, never the flag/error register.
- **Design system (chansu-design skill).** UI reuses the `.cs-*` class contract (add classes, never repurpose); three type registers (Sans interface / Mono machine-data / Serif chemistry via `chem()`); §7 states; §8 voice (no em dashes, no AI lexis). Run the `chansu-theme-review` skill on the UI before committing it.
- **Commits.** Luke's standing rule: never commit or push without his explicit OK. The `git commit` steps below are the intended boundaries; during execution, surface the staged change and get his go (or he runs `/ship`).

**Working directory:** the `feature/compound-ingestion` worktree (`.claude/worktrees/compound-ingestion/`). All paths below are repo-relative within it.

---

### Task 1: Ingest report types + vocabulary derivation

**Files:**
- Create: `chansu/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Produces: `Check(level: str, message: str, subject: Optional[str]=None, link: Optional[str]=None)`; `IngestReport(ok: bool, record: dict, checks: list, compound_id: Optional[str]=None)` with `.fails` and `.flags` properties; `derive_vocabulary(strategies: list) -> tuple[set, set]` returning `(attachment_types, liability_classes)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest.py
from chansu import ingest
from chansu.core.loaders import load_strategies


def test_derive_vocabulary_unions_the_library():
    attach, liab = ingest.derive_vocabulary(load_strategies())
    # the library keys on liability class + attachment type; both sets are non-empty
    assert attach and liab
    assert all(isinstance(x, str) for x in attach | liab)


def test_report_partitions_checks_by_level():
    checks = [ingest.Check("fail", "a"), ingest.Check("flag", "b"), ingest.Check("pass", "c")]
    report = ingest.IngestReport(ok=False, record={}, checks=checks)
    assert [c.message for c in report.fails] == ["a"]
    assert [c.message for c in report.flags] == ["b"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -q`
Expected: FAIL (module `chansu.ingest` does not exist).

- [ ] **Step 3: Write minimal implementation**

```python
# chansu/ingest.py
"""Deterministic ingest gate: validate an externally-authored compound record, report every
check transparently (never raise past the boundary), and write a passing record into data/.

Pure Python (RDKit for structure only) — no model, no Streamlit; reusable by the UI and a
future MCP surface. Generic (PROJECT.md §5): it reads generic fields and derives its controlled
vocabulary from the strategy library at runtime; it invents nothing (§6).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rdkit import Chem

from .core.loaders import compound_from_dict, data_dir
from .references import _parse_source


@dataclass
class Check:
    """One gate check. ``level`` is ``pass`` | ``info`` | ``flag`` | ``fail``. A ``fail`` blocks
    the write (the record cannot become a molecule); a ``flag`` is shown and acknowledged, never
    silently allowed. ``link`` carries a PubMed/DOI URL when relevant."""

    level: str
    message: str
    subject: Optional[str] = None
    link: Optional[str] = None


@dataclass
class IngestReport:
    """The full, transparent outcome of validating one record (every check kept, pass or fail —
    no silent omission). ``ok`` is True when there are no hard failures; flags may still need a
    human acknowledgement in the UI."""

    ok: bool
    record: dict
    checks: list = field(default_factory=list)
    compound_id: Optional[str] = None

    @property
    def fails(self) -> list:
        return [c for c in self.checks if c.level == "fail"]

    @property
    def flags(self) -> list:
        return [c for c in self.checks if c.level == "flag"]


def derive_vocabulary(strategies: list) -> tuple:
    """(attachment_types, liability_classes) — the union across the strategy library. The gate
    lints a record against this so an off-vocabulary handle/liability becomes visible instead of
    silently degrading. Data-derived, never hardcoded (§5)."""
    attach: set = set()
    liab: set = set()
    for s in strategies:
        attach.update(s.attachment_types)
        liab.update(s.liability_classes)
    return attach, liab
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit** (get Luke's OK first)

```bash
git add chansu/ingest.py tests/test_ingest.py
git commit -m "feat(ingest): report types + library vocabulary derivation"
```

---

### Task 2: Structural validation (hard fails) + `validate_record`

**Files:**
- Modify: `chansu/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `Check`, `IngestReport`, `derive_vocabulary` (Task 1).
- Produces: `validate_record(record: dict, strategies: list, existing_ids=frozenset()) -> IngestReport` (structural checks only in this task); helper `_structural_checks(record: dict, existing_ids) -> tuple[list, Optional[Mol], Optional[str]]` returning `(checks, mol, canonical_smiles)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest.py  (append)
_VALID = {
    "id": "demo_compound",
    "name": "Demo compound",
    "structure": {"smiles": "CC(=O)Oc1ccccc1C(=O)O", "source": "PubChem", "source_id": "CID 2244"},
    "liabilities": [{"kind": "poor_solubility", "detail": "x",
                     "citation": {"label": "A 2020", "source": "PMID 12345678"}}],
}


def _levels(report, subject):
    return {c.level for c in report.checks if c.subject == subject}


def test_valid_record_has_no_hard_fail_and_canonicalizes():
    report = ingest.validate_record(_VALID, load_strategies())
    assert report.ok
    assert not report.fails
    # SMILES is canonicalized in the returned record
    assert report.record["structure"]["smiles"] == "CC(=O)Oc1ccccc1C(=O)O"


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
    bad = {**_VALID, "importance_map": [{"id": "r1", "importance": "high", "reason": "x",
                                         "locator": {"smarts": "[[bad"}}]}
    report = ingest.validate_record(bad, load_strategies())
    assert not report.ok
    assert any(c.level == "fail" and c.subject == "importance_map" for c in report.checks)


def test_duplicate_liability_kind_hard_fails():
    bad = {**_VALID, "liabilities": [
        {"kind": "poor_solubility", "citation": {"label": "A", "source": "PMID 1"}},
        {"kind": "poor_solubility", "citation": {"label": "B", "source": "PMID 2"}}]}
    report = ingest.validate_record(bad, load_strategies())
    assert not report.ok
    assert any(c.level == "fail" and c.subject == "liabilities" for c in report.checks)


def test_id_collision_flags_not_fails():
    report = ingest.validate_record(_VALID, load_strategies(), existing_ids={"demo_compound"})
    assert report.ok  # a flag does not block
    assert any(c.level == "flag" and c.subject == "id" for c in report.checks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -q`
Expected: FAIL (`validate_record` not defined).

- [ ] **Step 3: Write minimal implementation** (append to `chansu/ingest.py`)

```python
_REQUIRED = ("id", "name")


def _structural_checks(record: dict, existing_ids) -> tuple:
    """Hard structural validation. Returns (checks, mol, canonical_smiles); ``mol`` is None when
    the SMILES is missing or invalid, so advisory checks (Task 3) are skipped."""
    checks: list = []
    for key in _REQUIRED:
        if not record.get(key):
            checks.append(Check("fail", f"Missing required field: {key}.", subject=key))

    smiles = (record.get("structure") or {}).get("smiles")
    mol = None
    canonical = None
    if not smiles:
        checks.append(Check("fail", "Missing required field: structure.smiles.", subject="structure.smiles"))
    else:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            checks.append(Check("fail", "structure.smiles is not a valid molecule.", subject="structure.smiles"))
        else:
            canonical = Chem.MolToSmiles(mol)
            checks.append(Check("pass", "Structure parses and canonicalizes.", subject="structure.smiles"))

    for kind in ("modifiable_positions", "importance_map"):
        for i, item in enumerate(record.get(kind, [])):
            smarts = (item.get("locator") or {}).get("smarts")
            if not smarts:
                checks.append(Check("fail", f"{kind}[{i}] locator has no smarts.", subject=kind))
            elif Chem.MolFromSmarts(smarts) is None:
                checks.append(Check("fail", f"{kind}[{i}] locator smarts is invalid: {smarts!r}.", subject=kind))

    kinds = [l.get("kind") for l in record.get("liabilities", []) if l.get("kind")]
    dupes = sorted({k for k in kinds if kinds.count(k) > 1})
    if dupes:
        checks.append(Check("fail", f"Duplicate liability kind(s): {dupes}. Kind is the grouping key and must be unique.",
                            subject="liabilities"))

    rid = record.get("id")
    if rid and rid in existing_ids:
        checks.append(Check("flag", f"A compound with id {rid!r} already exists; importing overwrites it.", subject="id"))

    return checks, mol, canonical


def validate_record(record: dict, strategies: list, existing_ids=frozenset()) -> IngestReport:
    """Validate a raw compound record and return a full, transparent report. Never raises on bad
    input — a malformed record produces ``fail`` checks, not an exception."""
    checks, mol, canonical = _structural_checks(record, existing_ids)
    ok = not any(c.level == "fail" for c in checks)
    out = record
    if canonical:
        out = {**record, "structure": {**record.get("structure", {}), "smiles": canonical}}
    return IngestReport(ok=ok, record=out, checks=checks, compound_id=record.get("id"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -q`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 5: Commit** (get Luke's OK first)

```bash
git add chansu/ingest.py tests/test_ingest.py
git commit -m "feat(ingest): structural validation (hard fails) + validate_record"
```

---

### Task 3: Advisory checks (locator resolution, vocabulary lint, citations)

**Files:**
- Modify: `chansu/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `validate_record`, `_structural_checks`, `derive_vocabulary`, `_parse_source`.
- Produces: `_advisory_checks(record: dict, mol, attach_vocab: set, liab_vocab: set) -> list`; `validate_record` now appends advisory checks when the structure is valid.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest.py  (append)
def test_unresolvable_locator_flags():
    # a valid SMARTS that matches nothing on aspirin (a phosphorus atom)
    rec = {**_VALID, "importance_map": [{"id": "r1", "importance": "high", "reason": "x",
                                         "locator": {"smarts": "[P]", "label": "phantom"}}]}
    report = ingest.validate_record(rec, load_strategies())
    assert report.ok  # advisory, not blocking
    assert any(c.level == "flag" and "matches no site" in c.message for c in report.checks)


def test_offvocab_liability_flags():
    rec = {**_VALID, "liabilities": [{"kind": "definitely_not_a_library_class",
                                      "citation": {"label": "A", "source": "PMID 1"}}]}
    report = ingest.validate_record(rec, load_strategies())
    assert any(c.level == "flag" and c.subject == "liabilities" for c in report.checks)


def test_uncited_claim_flags():
    rec = {**_VALID, "targets": [{"name": "SomeTarget"}]}  # no citation
    report = ingest.validate_record(rec, load_strategies())
    assert any(c.level == "flag" and c.subject == "targets" for c in report.checks)


def test_cited_claim_gets_a_link_not_a_flag():
    rec = {**_VALID, "targets": [{"name": "SomeTarget",
                                  "citation": {"label": "A 2020", "source": "PMID 20388710"}}]}
    report = ingest.validate_record(rec, load_strategies())
    target_checks = [c for c in report.checks if c.subject == "targets"]
    assert target_checks and all(c.level != "flag" for c in target_checks)
    assert any(c.link and "pubmed" in c.link for c in target_checks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -q`
Expected: FAIL (advisory checks not yet emitted).

- [ ] **Step 3: Write minimal implementation** (append helper + edit `validate_record`)

```python
def _citation_checks(kind: str, items: list, label_key: str) -> list:
    checks: list = []
    for item in items:
        label = item.get(label_key) or kind
        cit = item.get("citation") or {}
        pmid, doi, _urls = _parse_source(cit.get("source"))
        if not cit.get("label") or (not pmid and not doi):
            checks.append(Check("flag",
                                f"{kind} {label!r} has no verifiable citation (PMID/DOI); tagged uncited until confirmed.",
                                subject=kind))
        else:
            link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else f"https://doi.org/{doi}"
            checks.append(Check("info", f"{kind} {label!r}: citation identifier present. Confirm before trusting.",
                                subject=kind, link=link))
    return checks


def _advisory_checks(record: dict, mol, attach_vocab: set, liab_vocab: set) -> list:
    """Soft, non-blocking checks: locator resolution on the real molecule, controlled-vocabulary
    lint against the library, and per-claim citation verifiability. These make silent degradation
    visible; they never block a write (§6 honesty, not gatekeeping)."""
    checks: list = []
    for kind in ("modifiable_positions", "importance_map"):
        for i, item in enumerate(record.get(kind, [])):
            smarts = (item.get("locator") or {}).get("smarts")
            patt = Chem.MolFromSmarts(smarts) if smarts else None
            if patt is None:
                continue  # invalid smarts already hard-failed in Task 2
            n = len(mol.GetSubstructMatches(patt))
            label = (item.get("locator") or {}).get("label") or item.get("id") or f"{kind}[{i}]"
            if n == 0:
                checks.append(Check("flag", f"Locator {label!r} matches no site on this structure.", subject=kind))
            elif n > 1:
                checks.append(Check("info", f"Locator {label!r} matches {n} sites; the engine acts on the first.", subject=kind))

    for p in record.get("modifiable_positions", []):
        types = set(p.get("attachment_types", []))
        if types and not (types & attach_vocab):
            checks.append(Check("flag",
                                f"Attachment type(s) {sorted(types)} match no strategy; generation will describe-only.",
                                subject="modifiable_positions"))

    for l in record.get("liabilities", []):
        kind = l.get("kind")
        if kind and kind not in liab_vocab:
            checks.append(Check("flag",
                                f"Liability {kind!r} matches no strategy in the current library; the tool will decline to over-claim.",
                                subject="liabilities"))

    checks += _citation_checks("targets", record.get("targets", []), "name")
    checks += _citation_checks("liabilities", record.get("liabilities", []), "kind")
    checks += _citation_checks("importance_map", record.get("importance_map", []), "id")
    return checks
```

Edit `validate_record` to append advisory checks when the structure parsed:

```python
def validate_record(record: dict, strategies: list, existing_ids=frozenset()) -> IngestReport:
    checks, mol, canonical = _structural_checks(record, existing_ids)
    if mol is not None:
        attach_vocab, liab_vocab = derive_vocabulary(strategies)
        checks += _advisory_checks(record, mol, attach_vocab, liab_vocab)
    ok = not any(c.level == "fail" for c in checks)
    out = record
    if canonical:
        out = {**record, "structure": {**record.get("structure", {}), "smiles": canonical}}
    return IngestReport(ok=ok, record=out, checks=checks, compound_id=record.get("id"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -q`
Expected: PASS (all ingest tests).

- [ ] **Step 5: Commit** (get Luke's OK first)

```bash
git add chansu/ingest.py tests/test_ingest.py
git commit -m "feat(ingest): advisory checks — locator resolution, vocab lint, citations"
```

---

### Task 4: Write a passing record into `data/compounds/`

**Files:**
- Modify: `chansu/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `IngestReport`, `validate_record`, `compound_from_dict`, `data_dir`.
- Produces: `write_record(report: IngestReport, source: Optional[str]=None, override: Optional[Path]=None) -> Path`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest.py  (append)
from chansu.core.loaders import load_compound


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
        assert False, "should have refused"
    except ValueError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -q`
Expected: FAIL (`write_record` not defined).

- [ ] **Step 3: Write minimal implementation** (append to `chansu/ingest.py`)

```python
def write_record(report: IngestReport, source: Optional[str] = None, override: Optional[Path] = None) -> Path:
    """Write a passing record to ``data/compounds/<id>.json``. Refuses a record with hard
    failures, and builds the Compound first as a final guard — never write something the loader
    cannot read. ``source`` stamps ``annotations.source`` so imported compounds stay distinguishable
    from curated ones."""
    if not report.ok:
        raise ValueError("cannot write a record with unresolved hard failures")
    record = report.record
    if source:
        record = {**record, "annotations": {**record.get("annotations", {}), "source": source}}
    compound_from_dict(record)  # final structural guard (raises if somehow still invalid)
    target = data_dir(override) / "compounds" / f"{record['id']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2))
    return target
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -q`
Expected: PASS.

- [ ] **Step 5: Commit** (get Luke's OK first)

```bash
git add chansu/ingest.py tests/test_ingest.py
git commit -m "feat(ingest): write a validated record into data/compounds"
```

---

### Task 5: Prompt builder (pure Python) + Claude Science project setup

**Files:**
- Create: `chansu/ingest_prompts.py`
- Test: `tests/test_ingest_prompts.py`

**Interfaces:**
- Produces: constants `PROJECT_NAME`, `PROJECT_DESCRIPTION`, `AGENT_CONTEXT`, `RECORD_SCHEMA`; `build_project_setup() -> str`; `build_review_prompt(name: str, vocabulary: tuple, liability_focus: Optional[str]=None) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest_prompts.py
from chansu import ingest_prompts as p


def test_project_setup_names_the_trust_boundary():
    setup = p.build_project_setup()
    assert p.PROJECT_NAME in setup
    low = setup.lower()
    assert "pubmed" in low and "fabricate" in low  # citation discipline is stated


def test_review_prompt_injects_name_schema_and_vocabulary():
    prompt = p.build_review_prompt("Curcumin", vocabulary=({"hydroxyl", "carboxyl"}, {"poor_solubility"}))
    assert "Curcumin" in prompt
    assert "smiles" in prompt.lower()          # schema is embedded
    assert "hydroxyl" in prompt                 # vocabulary is embedded
    assert "poor_solubility" in prompt


def test_review_prompt_optional_liability_focus():
    prompt = p.build_review_prompt("Curcumin", vocabulary=(set(), set()), liability_focus="rapid_clearance")
    assert "rapid_clearance" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ingest_prompts.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

```python
# chansu/ingest_prompts.py
"""Pure-Python prompt builder for the Claude Science import path (Path A). No model, no network:
it emits the one-time Claude Science project setup and a per-compound review prompt that asks for
exactly the record the ingest gate validates. Generic (§5): the text names no specific compound;
the controlled vocabulary is injected by the caller from the loaded library."""
from __future__ import annotations

from typing import Optional

PROJECT_NAME = "Chansu Compound Grounding"

PROJECT_DESCRIPTION = (
    "Extraction of grounded, citation-backed structured records for medicinal-chemistry compounds, "
    "for import into Chansu (a generic compound-modification tool). For a named natural compound "
    "with known therapeutic activity, produce its molecular targets, druggability liabilities, "
    "activity-essential regions, and modifiable handles, each backed by a real, PubMed-verifiable "
    "citation. Never fabricate a citation, a structure, or a number. Where a fact cannot be grounded, "
    "leave it empty and say so."
)

AGENT_CONTEXT = (
    "You extract structured compound records for Chansu, a medicinal-chemistry tool with a strict "
    "trust boundary: literature is grounded and cited; structures and properties are computed "
    "deterministically downstream; every claim is provenance-tagged. Your job is the literature "
    "grounding only.\n\n"
    "For the compound you are given, identify its molecular target(s) and role; its druggability "
    "liabilities (for example toxicity, poor solubility, rapid clearance, poor selectivity); the "
    "regions essential for activity, graded high / medium / low; and the positions that are "
    "reasonable medicinal-chemistry handles to modify. Back every target, liability, and importance "
    "claim with a real citation carrying a PMID and/or DOI that resolves on PubMed. Prefer primary "
    "literature. Do not invent authors, years, identifiers, or numbers; if you are unsure a citation "
    "is real, omit it. Provide a canonical SMILES from a named source (for example PubChem, with the "
    "CID), not from memory. Do not predict binding affinity, toxicity, or efficacy, and do not claim "
    "a liability is solved: you ground facts; the tool reasons and computes. Where a field cannot be "
    "grounded, leave it empty and note what is missing. An honest gap is correct; a fabricated fill "
    "is a failure."
)

RECORD_SCHEMA = """{
  "id": "<slug, lowercase_with_underscores>",
  "name": "<display name>",
  "structure": {"smiles": "<canonical SMILES>", "source": "PubChem", "source_id": "CID <n>", "inchikey": "<key>"},
  "targets": [{"name": "<target>", "role": "<role>", "citation": {"label": "<full citation>", "source": "PMID <n> | DOI <doi>"}}],
  "liabilities": [{"kind": "<liability kind>", "detail": "<detail>", "citation": {"label": "<full citation>", "source": "PMID <n> | DOI <doi>"}}],
  "importance_map": [{"id": "<slug>", "importance": "high|medium|low", "reason": "<why>", "locator": {"smarts": "<SMARTS>", "label": "<label>"}, "citation": {"label": "<full citation>", "source": "PMID <n>"}}],
  "modifiable_positions": [{"id": "<slug>", "label": "<label>", "attachment_types": ["<type>"], "locator": {"smarts": "<SMARTS>", "label": "<label>"}}],
  "gaps": ["<anything you could not ground with a real citation>"]
}"""


def build_project_setup() -> str:
    """The one-time text pasted into a Claude Science project's settings (permanent)."""
    return (
        f"Project name:\n{PROJECT_NAME}\n\n"
        f"Project description:\n{PROJECT_DESCRIPTION}\n\n"
        f"Agent context:\n{AGENT_CONTEXT}\n"
    )


def build_review_prompt(name: str, vocabulary: tuple, liability_focus: Optional[str] = None) -> str:
    """The per-compound prompt the chemist pastes into Claude Science. ``vocabulary`` is
    ``(attachment_types, liability_classes)`` from the loaded library (``ingest.derive_vocabulary``)."""
    attach, liab = vocabulary
    focus = f" Focus especially on the liability: {liability_focus}." if liability_focus else ""
    return (
        f"Produce a Chansu compound record for {name}.{focus}\n\n"
        "Ground and return, each with a real PMID/DOI citation: a canonical SMILES with its source "
        "(for example a PubChem CID) and InChIKey if available; molecular targets (name + role); "
        "druggability liabilities (kind + detail); activity-essential regions graded high / medium / "
        "low, each with a reason and a locator SMARTS; and modifiable positions (label + attachment "
        "type + locator SMARTS).\n\n"
        f"Emit exactly this JSON, filling every field you can ground and listing anything you cannot "
        f"under \"gaps\":\n{RECORD_SCHEMA}\n\n"
        f"Controlled vocabulary. Attachment types: {sorted(attach)}. Liability kinds: {sorted(liab)}. "
        "Use these where they fit so the record lines up with the strategy library.\n\n"
        "Rules: real citations only, verifiable on PubMed (PMID and/or DOI); no invented authors, "
        "years, or numbers; SMILES from a named source, not memory; do not predict binding, toxicity, "
        "or efficacy. If a fact cannot be grounded, leave it empty and say so under \"gaps\"."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ingest_prompts.py -q`
Expected: PASS.

- [ ] **Step 5: Verify the §5 generic-engine test still passes** (the new text must contain no banned token)

Run: `.venv/bin/python -m pytest tests/test_core.py -q`
Expected: PASS.

- [ ] **Step 6: Commit** (get Luke's OK first)

```bash
git add chansu/ingest_prompts.py tests/test_ingest_prompts.py
git commit -m "feat(ingest): pure-Python prompt builder + Claude Science project setup"
```

---

### Task 6: The "Add compound" tab (Streamlit) + wire into the app

**Files:**
- Create: `chansu/ui/ingest.py`
- Modify: `chansu/ui/app.py:89-95` (add the tab)
- Test: `tests/test_ui_ingest_import.py` (import-smoke only — Streamlit rendering is verified in the browser preview)

**Interfaces:**
- Consumes: `ingest.validate_record`, `ingest.write_record`, `ingest.derive_vocabulary`, `ingest_prompts.build_project_setup`, `ingest_prompts.build_review_prompt`, `state.get_strategies`, `state.available_compound_ids`.
- Produces: `render_ingest(strategies: list) -> None`.

This task is build-and-verify-in-preview, not pytest-TDD (Streamlit UI). Keep every rendered string in the §8 voice and every element on the `.cs-*` contract; run `chansu-theme-review` before the commit.

- [ ] **Step 1: Invoke the chansu-design skill** and keep the token/class reference open. The gate report maps to states directly: `pass` → `.cs-pass`; `fail` → `.cs-flagcard` + `.cs-flag` (`--high`); `flag`/`info`/uncited → calm `.cs-declined`; citations → `.cs-cite` + a `.cs-prov` (`lit`/`uncited`) tag + the PubMed/DOI link. SMILES/identifiers in mono; formulae/names via `chem()`/`formula()`.

- [ ] **Step 2: Write the import-smoke test**

```python
# tests/test_ui_ingest_import.py
def test_render_ingest_is_importable():
    # Importing the UI module must not require a running Streamlit context or a model.
    from chansu.ui import ingest as ui_ingest
    assert hasattr(ui_ingest, "render_ingest")
```

- [ ] **Step 3: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ui_ingest_import.py -q`
Expected: FAIL (module missing).

- [ ] **Step 4: Write `chansu/ui/ingest.py`**

```python
"""Screen: "Add compound" — bring a new compound in from a literature review (Path A).

Three sections: a pure-Python prompt builder, a paste/upload record gate (Producer A), and a
placeholder for model-assisted research-log structuring (Producer B, arrives with the model
layer). Deterministic: no model runs here. Every claim is provenance-tagged; declines and
unverified citations render calm (`.cs-declined`), never as errors. This module arranges and
displays only (chansu-design skill)."""
from __future__ import annotations

import html
import json

import streamlit as st

from ..ingest import derive_vocabulary, validate_record, write_record
from ..ingest_prompts import build_project_setup, build_review_prompt
from . import state
from .notation import chem

_LEVEL_CLASS = {"pass": "cs-pass", "fail": "cs-flagcard", "flag": "cs-declined", "info": "cs-declined"}


def _prompt_builder() -> None:
    st.markdown("<p class='cs-eyebrow'>Prompt builder</p>", unsafe_allow_html=True)
    st.markdown("<div class='cs-sub'>Pure Python, no model. Name a compound; copy the prompt into a "
                "Claude Science project, then paste its record below.</div>", unsafe_allow_html=True)
    name = st.text_input("Compound name", key="ingest_name", placeholder="e.g. Curcumin")
    focus = st.text_input("Liability focus (optional)", key="ingest_focus", placeholder="e.g. poor_solubility")
    if name:
        vocab = derive_vocabulary(state.get_strategies())
        st.markdown("<p class='cs-eyebrow' style='margin-top:12px'>Per-compound prompt</p>", unsafe_allow_html=True)
        st.code(build_review_prompt(name, vocab, focus or None), language="text")
    with st.expander("One-time Claude Science project setup"):
        st.code(build_project_setup(), language="text")


def _render_report(report) -> None:
    for c in report.checks:
        cls = _LEVEL_CLASS.get(c.level, "cs-sub")
        link = f" <a href='{html.escape(c.link)}' target='_blank'>source</a>" if c.link else ""
        st.markdown(f"<div class='{cls}' style='margin:4px 0'>{chem(c.message, serif=False)}{link}</div>",
                    unsafe_allow_html=True)


def _paste_and_gate() -> None:
    st.markdown("<p class='cs-eyebrow'>Paste or upload the record</p>", unsafe_allow_html=True)
    up = st.file_uploader("Record file (.json)", type=["json"], key="ingest_file")
    raw = st.text_area("…or paste the JSON record", key="ingest_raw", height=200)
    text = up.read().decode("utf-8") if up is not None else raw
    if not text.strip():
        return
    try:
        record = json.loads(text)
    except json.JSONDecodeError as exc:
        st.markdown(f"<div class='cs-flagcard'><span class='cs-flag'>flag</span>Not valid JSON: "
                    f"{html.escape(str(exc))}</div>", unsafe_allow_html=True)
        return

    existing = set(state.available_compound_ids())
    report = validate_record(record, state.get_strategies(), existing_ids=existing)
    _render_report(report)

    if not report.ok:
        st.markdown("<div class='cs-sub'>Fix the failures above, then re-validate. A record that cannot "
                    "become a molecule is not imported.</div>", unsafe_allow_html=True)
        return
    ack = True
    if report.flags:
        ack = st.checkbox("I have reviewed the flags above and want to import anyway.", key="ingest_ack")
    if st.button("Import compound", type="primary", disabled=not ack, key="ingest_import"):
        path = write_record(report, source="claude-science-import")
        state.available_compound_ids.clear()  # refresh the selector cache now, not in 60s
        st.markdown(f"<div class='cs-pass'>Imported <b>{html.escape(report.compound_id)}</b>. "
                    "Select it in the sidebar.</div>", unsafe_allow_html=True)


def render_ingest(strategies: list) -> None:
    st.markdown("<p class='cs-eyebrow'>Add compound</p>", unsafe_allow_html=True)
    st.markdown("<div class='cs-sub'>Bring a new compound in from a literature review. Validation is "
                "deterministic and provenance-honest; adding a compound is data only, never a code change.</div>",
                unsafe_allow_html=True)
    _prompt_builder()
    st.markdown("<hr class='cs-rule'>", unsafe_allow_html=True)
    _paste_and_gate()
    st.markdown("<hr class='cs-rule'>", unsafe_allow_html=True)
    st.markdown("<p class='cs-eyebrow'>Research-log structuring</p>"
                "<div class='cs-declined'>Model-assisted structuring of an existing research log arrives "
                "with the multi-model layer. Until then, use the prompt builder above and Claude Science.</div>",
                unsafe_allow_html=True)
```

- [ ] **Step 5: Wire the tab into `chansu/ui/app.py`** (modify `main()`)

Change the tabs line and add the render call:

```python
    workspace_tab, memo_tab, sources_tab, ingest_tab = st.tabs(
        ["Workspace", "Design memo", "Sources / Reference", "Add compound"]
    )
    with workspace_tab:
        render_workspace(compound, mol, result)
    with memo_tab:
        render_memo_tab(compound, mol, result, model)
    with sources_tab:
        render_sources(compound, state.get_strategies())
    with ingest_tab:
        from chansu.ui.ingest import render_ingest
        render_ingest(state.get_strategies())
```

- [ ] **Step 6: Run the import-smoke test**

Run: `.venv/bin/python -m pytest tests/test_ui_ingest_import.py -q`
Expected: PASS.

- [ ] **Step 7: Verify in the browser preview** (start `chansu-ui`, open the "Add compound" tab):
  - Prompt builder: type `Curcumin` → a prompt renders with the schema + vocabulary; the project-setup expander shows the permanent text.
  - Paste a **valid** minimal record → all-pass report, Import enabled → import → the compound appears in the sidebar selector without a restart.
  - Paste a record with a **bad SMILES** → a red `.cs-flagcard` fail, Import stays disabled.
  - Paste a record with an **uncited target** and an **unresolvable locator** → calm `.cs-declined` flags + an acknowledge checkbox gates Import.
  - Check console/logs are clean (`read_console_messages`, `preview_logs`).

- [ ] **Step 8: Run the full suite + the §5 guard**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all prior tests + the new ingest tests green; `test_generic_engine_rule` green).

- [ ] **Step 9: Run `chansu-theme-review`** on `chansu/ui/ingest.py` and address findings.

- [ ] **Step 10: Commit** (get Luke's OK first)

```bash
git add chansu/ui/ingest.py chansu/ui/app.py tests/test_ui_ingest_import.py
git commit -m "feat(ingest): Add-compound tab — prompt builder, paste/gate, import"
```

---

## Self-review

**Spec coverage:** contract/field-tiers → Tasks 2-3 (required/grounded/best-effort enforced by which checks are fail vs flag); gate hard-fail + soft-flag + two-way ack → Tasks 2, 3, 6; citations §6 → Task 3 + UI provenance rendering; prompt builder + permanent project setup → Task 5; Ingest page 3 sections → Task 6; storage + selector auto-discovery + `annotations.source` → Task 4 + Task 6 (`available_compound_ids.clear()`); Producer B → Task 6 placeholder (full build deferred, matches spec §6/§10). Covered.

**Placeholder scan:** no TBD/TODO; every code step carries complete code; the only `<...>` are inside `RECORD_SCHEMA`, which is intentional schema-template text shown to Claude Science.

**Type consistency:** `Check(level, message, subject, link)`, `IngestReport(ok, record, checks, compound_id)` with `.fails`/`.flags`, `validate_record(record, strategies, existing_ids)`, `write_record(report, source, override)`, `derive_vocabulary(strategies) -> (attach, liab)`, `build_review_prompt(name, vocabulary, liability_focus)` — used consistently across tasks and the UI.

## Out of scope (this plan)

Producer B model-assisted structuring (needs the multi-model layer); hosted MCP connector; live NCBI author/title verification; any model in the builder or gate; binding/toxicity/efficacy prediction.

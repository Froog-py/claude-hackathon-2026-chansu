"""Deterministic ingest gate: validate an externally-authored compound record, report every
check transparently (never raise past the boundary), and write a passing record into data/.

Pure Python (RDKit for structure only) — no model, no Streamlit; reusable by the UI and a future
MCP surface. Generic (PROJECT.md §5): it reads generic fields and derives its controlled
vocabulary from the strategy library at runtime; it invents nothing (§6). A malformed record
becomes ``fail`` checks in a report, never an exception thrown at the caller.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rdkit import Chem

from .core.loaders import compound_from_dict, data_dir
from .references import _parse_source


@dataclass
class Check:
    """One gate check. ``level`` is ``pass`` | ``info`` | ``flag`` | ``fail``. A ``fail`` blocks the
    write (the record cannot become a molecule); a ``flag`` is shown and acknowledged, never
    silently allowed. ``link`` carries a PubMed/DOI URL when relevant."""

    level: str
    message: str
    subject: Optional[str] = None
    link: Optional[str] = None


@dataclass
class IngestReport:
    """The full, transparent outcome of validating one record — every check kept, pass or fail, so
    nothing is silently omitted. ``ok`` is True when there are no hard failures; flags may still
    need a human acknowledgement in the UI before the write."""

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
    """(attachment_types, liability_classes) — the union across the strategy library. The gate lints
    a record against this so an off-vocabulary handle or liability becomes visible instead of
    silently degrading to describe-only. Data-derived, never hardcoded (§5)."""
    attach: set = set()
    liab: set = set()
    for s in strategies:
        attach.update(s.attachment_types)
        liab.update(s.liability_classes)
    return attach, liab


_REQUIRED = ("id", "name")
# id becomes a filename (data/compounds/<id>.json); constrain it to a safe slug so a crafted id
# cannot traverse the path or produce an unreadable file.
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")


def _structural_checks(record: dict, existing_ids) -> tuple:
    """Hard structural validation. Returns (checks, mol, canonical_smiles); ``mol`` is None when the
    SMILES is missing or invalid, so the advisory checks are skipped."""
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
        checks.append(Check(
            "fail",
            f"Duplicate liability kind(s): {dupes}. Kind is the grouping key and must be unique.",
            subject="liabilities",
        ))

    rid = record.get("id")
    if rid and not _ID_RE.match(str(rid)):
        checks.append(Check("fail", f"id {rid!r} is not a safe slug (lowercase letters, digits, underscores only).", subject="id"))
    if rid and rid in existing_ids:
        checks.append(Check("flag", f"A compound with id {rid!r} already exists; importing overwrites it.", subject="id"))

    return checks, mol, canonical


def _citation_checks(kind: str, items: list, label_key: str) -> list:
    """One check per claim: a citation with a resolvable PMID/DOI links out for confirmation;
    anything else is flagged uncited (§6 — a citation is never fabricated or auto-verified)."""
    checks: list = []
    for item in items:
        label = item.get(label_key) or kind
        cit = item.get("citation") or {}
        pmid, doi, _urls = _parse_source(cit.get("source"))
        if not cit.get("label") or (not pmid and not doi):
            checks.append(Check(
                "flag",
                f"{kind} {label!r} has no verifiable citation (PMID/DOI); tagged uncited until confirmed.",
                subject=kind,
            ))
        else:
            link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else f"https://doi.org/{doi}"
            checks.append(Check(
                "info", f"{kind} {label!r}: citation identifier present. Confirm before trusting.",
                subject=kind, link=link,
            ))
    return checks


def _advisory_checks(record: dict, mol, attach_vocab: set, liab_vocab: set) -> list:
    """Soft, non-blocking checks: locator resolution on the real molecule, controlled-vocabulary
    lint against the library, and per-claim citation verifiability. These make silent degradation
    visible; they never block a write (§6 is honesty, not gatekeeping)."""
    checks: list = []
    for kind in ("modifiable_positions", "importance_map"):
        for i, item in enumerate(record.get(kind, [])):
            smarts = (item.get("locator") or {}).get("smarts")
            patt = Chem.MolFromSmarts(smarts) if smarts else None
            if patt is None:
                continue  # invalid smarts already hard-failed in _structural_checks
            n = len(mol.GetSubstructMatches(patt))
            label = (item.get("locator") or {}).get("label") or item.get("id") or f"{kind}[{i}]"
            if n == 0:
                checks.append(Check("flag", f"Locator {label!r} matches no site on this structure.", subject=kind))
            elif n > 1:
                checks.append(Check("info", f"Locator {label!r} matches {n} sites; the engine acts on the first.", subject=kind))

    for p in record.get("modifiable_positions", []):
        types = set(p.get("attachment_types", []))
        if types and not (types & attach_vocab):
            checks.append(Check(
                "flag",
                f"Attachment type(s) {sorted(types)} match no strategy; generation will describe-only.",
                subject="modifiable_positions",
            ))

    for l in record.get("liabilities", []):
        kind = l.get("kind")
        if kind and kind not in liab_vocab:
            checks.append(Check(
                "flag",
                f"Liability {kind!r} matches no strategy in the current library; the tool will decline to over-claim.",
                subject="liabilities",
            ))

    checks += _citation_checks("targets", record.get("targets", []), "name")
    checks += _citation_checks("liabilities", record.get("liabilities", []), "kind")
    checks += _citation_checks("importance_map", record.get("importance_map", []), "id")
    return checks


def validate_record(record: dict, strategies: list, existing_ids=frozenset()) -> IngestReport:
    """Validate a raw compound record and return a full, transparent report. Never raises on bad
    input — a malformed record produces ``fail`` checks, not an exception. ``existing_ids`` lets the
    caller flag (not block) an id that would overwrite an existing compound."""
    checks, mol, canonical = _structural_checks(record, existing_ids)
    if mol is not None:
        attach_vocab, liab_vocab = derive_vocabulary(strategies)
        checks += _advisory_checks(record, mol, attach_vocab, liab_vocab)
    ok = not any(c.level == "fail" for c in checks)
    out = record
    if canonical:
        out = {**record, "structure": {**record.get("structure", {}), "smiles": canonical}}
    return IngestReport(ok=ok, record=out, checks=checks, compound_id=record.get("id"))


def write_record(report: IngestReport, source: Optional[str] = None, override: Optional[Path] = None) -> Path:
    """Write a passing record to ``data/compounds/<id>.json``. Refuses a record with hard failures,
    and builds the Compound first as a final guard — never write something the loader cannot read.
    ``source`` stamps ``annotations.source`` so imported compounds stay distinguishable from
    curated ones."""
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

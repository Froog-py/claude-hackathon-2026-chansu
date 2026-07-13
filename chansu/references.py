"""The Reference workspace index (PROJECT.md §9) — aggregate the citations that already exist in the data.

Every scientific claim in a compound (targets, liabilities, importance regions) and every strategy in the
library already carries a real ``Citation`` (never fabricated, §6). This module walks those citations,
dedupes them by paper (DOI/PMID), and aggregates *what each paper backs* — producing a Zotero-style,
groupable reference list for the Sources screen with **no new data authoring**.

Generic and framework-agnostic: it reads ``Citation`` objects wherever they hang and invents nothing. No
compound knowledge, no RDKit, no Streamlit — unit-testable on its own and reusable by any front-end (and
by the future MCP surface).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .core.models import Citation, Compound, Strategy

_PMID_RE = re.compile(r"PMID[:\s]*([0-9]+)", re.IGNORECASE)
_DOI_RE = re.compile(r"(10\.[0-9]{4,9}/[^\s|]+)")
_URL_RE = re.compile(r"(https?://[^\s|]+)")


@dataclass
class Reference:
    """One deduped paper and everything it grounds. ``roles`` are the kinds of claim it backs
    (``target`` / ``liability`` / ``importance`` / ``strategy-precedent``); ``subjects`` are the specific
    things (target names, liability kinds, region labels, strategy ids); ``backs`` is the per-claim
    ``(role, subject)`` detail for the expander. ``urls`` are derived PubMed/DOI links plus any bare URL."""

    key: str
    citation: str                                  # the full formatted citation string (Citation.label)
    pmid: Optional[str] = None
    doi: Optional[str] = None
    urls: list = field(default_factory=list)
    roles: list = field(default_factory=list)
    subjects: list = field(default_factory=list)
    backs: list = field(default_factory=list)      # list[(role, subject)]
    notes: list = field(default_factory=list)      # distinct Citation.notes across every citing claim


def _parse_source(source: Optional[str]) -> tuple:
    """Pull a PMID, a DOI, and any bare URLs out of a free-form ``Citation.source`` string like
    ``"PMID 20388710 | DOI 10.1074/jbc.M110.119248"``. Any of them may be absent."""
    if not source:
        return None, None, []
    pmid_m = _PMID_RE.search(source)
    doi_m = _DOI_RE.search(source)
    pmid = pmid_m.group(1) if pmid_m else None
    doi = doi_m.group(1).rstrip(".").rstrip("|").strip() if doi_m else None
    urls = [u.rstrip(".") for u in _URL_RE.findall(source)]
    return pmid, doi, urls


def _initial_key(pmid: Optional[str], doi: Optional[str], label: str) -> str:
    """A stable key for a freshly-seen paper. Dedupe across claims is done by *shared identifier*
    (see ``_find_existing``), not by this key — the key is only a fallback identity for label-only
    citations that carry no PMID/DOI."""
    if doi:
        return f"doi:{doi.lower()}"
    if pmid:
        return f"pmid:{pmid}"
    return f"label:{label.strip().lower()}"


def build_reference_index(compound: Compound, strategies: list) -> list:
    """Deduped, aggregated reference list for ``compound`` plus the strategy ``library``. Each paper cited
    by several claims collapses to one ``Reference`` recording every role/subject/claim/note it backs.

    Dedupe is by *any shared identifier* (same PMID or same DOI), so a paper cited once with a full
    ``PMID | DOI`` and once with only one of them still collapses to a single entry — important for
    heterogeneous citations from an external source (e.g. the Claude Science connector). Notes are
    aggregated across every citing claim, not taken only from the first (they are the extract-once /
    reuse-many provenance trail, §9)."""
    refs: list = []

    def _find_existing(pmid: Optional[str], doi: Optional[str], label_key: str):
        for ref in refs:
            if pmid and ref.pmid == pmid:
                return ref
            if doi and ref.doi and ref.doi.lower() == doi.lower():
                return ref
            if not pmid and not doi and label_key in (ref.key, f"label:{ref.citation.strip().lower()}"):
                return ref  # a label-only citation reuses any ref with the same label, incl. identifier-backed
        return None

    def _add_url(ref: Reference, url: Optional[str]) -> None:
        if url and url not in ref.urls:
            ref.urls.append(url)

    def add(citation: Optional[Citation], role: str, subject: str) -> None:
        if citation is None or not citation.label:
            return  # only real, cited papers enter the index (§6)
        pmid, doi, urls = _parse_source(citation.source)
        label_key = f"label:{(citation.label or '').strip().lower()}"
        ref = _find_existing(pmid, doi, label_key)
        if ref is None:
            ref = Reference(
                key=_initial_key(pmid, doi, citation.label), citation=citation.label, pmid=pmid, doi=doi,
            )
            for url in urls:
                _add_url(ref, url)
            if pmid:
                _add_url(ref, f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
            if doi:
                _add_url(ref, f"https://doi.org/{doi}")
            refs.append(ref)
        else:
            # a later citation of the same paper may carry an identifier the first-seen one lacked
            if ref.pmid is None and pmid:
                ref.pmid = pmid
                _add_url(ref, f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
            if ref.doi is None and doi:
                ref.doi = doi
                _add_url(ref, f"https://doi.org/{doi}")
            for url in urls:
                _add_url(ref, url)
        if role not in ref.roles:
            ref.roles.append(role)
        if subject not in ref.subjects:
            ref.subjects.append(subject)
        ref.backs.append((role, subject))
        if citation.note and citation.note not in ref.notes:
            ref.notes.append(citation.note)

    for target in compound.targets:
        add(target.citation, "target", target.name)
    for liability in compound.liabilities:
        add(liability.citation, "liability", liability.kind)
    for region in compound.importance_map:
        add(region.citation, "importance", region.locator.label or region.id)
    for strategy in strategies:
        add(strategy.citation, "strategy-precedent", strategy.id)

    for ref in refs:
        ref.roles.sort()
    return refs

# Chansu — compound ingestion (design)

Design spec for bringing a **new compound** into Chansu from a literature review, with no engine
change (adding a compound stays data-only, PROJECT.md §5). Companion to
[`day5-streamlit-ui-design.md`](day5-streamlit-ui-design.md) and the chansu-design system.

## Status and scope

- **Path A — Claude Science import.** Detailed here. **Built first.**
- **Producer B — research-log structuring.** Architected-for and scoped below; built later because
  it reuses the multi-model reasoning layer (a separate feature).
- **Hosted MCP connector.** Architected-for; a stretch / "coming soon" surface, not built here.

**The one line that governs the whole design:** the only places a model ever runs are **Producer B**
and the **reasoning page**. The **prompt builder** and the **ingest gate** are pure, deterministic
Python — no API call, so they cannot refuse, stall, or hallucinate. Authoring is off-sourced to
Claude Science; everything inside Chansu that touches the record is deterministic and provenance-honest.

## Problem

Chansu ships two curated compounds (bufalin, ursolic acid). There is no way to add a third without
hand-writing a JSON file. We want a chemist to bring a compound in from a Claude Science review
through a validated, honest pathway — and the historical record shows why the gate matters: bufalin
was grounded from a messy research log and **NCBI-verified** by hand; the ursolic-acid Claude Science
draft **mislabeled two citation authors** and used off-contract vocabulary (`docs/BUILD-LOG.md`).
Both producers we plan to support have already produced bad citations once. **Citation verification
is the load-bearing wall, no matter the source.**

## The pipeline at a glance

```
[Prompt builder]        pure Python — emits a copy-paste prompt + one-time project setup
      |  (chemist runs it in Claude Science, external, authoritative extraction)
      v
[Paste / upload]        the record comes back as JSON or markdown
      |
      v
[Ingest gate]           pure Python — RDKit structure + locator resolution + vocabulary lint
      |                 + per-citation PMID/DOI check. Hard-fail structural, soft-flag the rest.
      v
data/compounds/<id>.json  ->  appears in the sidebar selector (auto-discovered, §5 live)

Producer B (later): [raw log + configured model] -> partial draft (honest denial, prints gaps)
                     -> same ingest gate. "Hand it to Claude Science" routes uncertainty to Path A.
```

---

## 1. The contract — the compound record

The ingestion contract **is the existing compound JSON shape** ([`data/compounds/bufalin.json`](../data/compounds/bufalin.json),
loaded by `chansu/core/loaders.py:compound_from_dict`). We formalize it, we do not invent a new one.

**Field tiers** (lowering the bar for a successful import — SMARTS authoring is the hard part, see below):

| Tier | Fields | Gate behavior |
|---|---|---|
| **Required** | `id`, `name`, `structure.smiles` | Hard-fail if missing or invalid |
| **Grounded (expected)** | `targets[]`, `liabilities[]` (each with a real citation) | Import allowed without them, but flagged thin |
| **Best-effort** | `importance_map[]`, `modifiable_positions[]` (each needs a locator SMARTS) | Optional; can be added/edited after import |

A compound with only `structure + name + liabilities + targets` is a valid, useful import — the
deterministic pipeline already handles an empty `importance_map`/`modifiable_positions` (matching,
honest-failure, and the memo all render). The importance map and positions are the richest but
hardest fields (they require SMARTS), so they are best-effort at import.

**Controlled vocabulary.** `attachment_types` (on positions) and liability `kind`s must line up with
the strategy library's vocabulary or the match silently degrades to describe-only (the ursolic
lesson). The vocabulary is **derived at runtime from the library** (the union of `attachment_types`
and `liability_classes` across `data/strategies/*.json`) — never hardcoded in engine code (§5). The
gate lints against it and **warns, never errors**.

---

## 2. The ingest gate — `chansu/ingest.py`

A new pure-Python module (top level, beside `references.py` / `report.py`: framework-agnostic,
unit-testable, reusable by the UI and a future MCP surface). One entry point:

```
validate_record(record: dict, strategies: list) -> IngestReport
```

`IngestReport` carries an overall `ok` (may we write it?), the canonicalized record, and an ordered
list of `Check`s — each with a level (`fail` / `flag` / `info` / `pass`), a message, and an optional
citation/link. **Every check is shown**, pass or fail — this mirrors the reasoning-checks transparency
panel and Luke's directive (surface every check, never a silent omission).

**Hard-fail (structural — the record cannot become a molecule):**
- `structure.smiles` present and RDKit-parseable; canonicalize (stereo preserved). Invalid → fail.
- Required fields present (`id`, `name`); `id` is a safe filename slug.
- Every `locator.smarts` (in positions and importance regions) is valid SMARTS (RDKit). Invalid → fail.
- Liability `kind`s are unique (the grouping key; `compound_from_dict` already enforces this).

These reuse `compound_from_dict`'s existing validation — the gate runs it and **reports failures
transparently instead of raising**.

**Soft-flag (shown, acknowledged, not blocking):**
- A `locator.smarts` that resolves to **0 atoms** on this structure → flag *"locator matches no site."*
  (Exactly the ursolic silent-degradation case, now visible.)
- A locator that matches **>1 site** → info *"matches N sites; the engine acts on the first"*
  (the SOMEDAY multi-match note).
- **Vocabulary lint:** an `attachment_type` or liability `kind` that intersects **no** strategy →
  flag *"matches nothing in the current library; generation will describe-only."*
- **Citations (§6):** for each target / liability / importance claim, parse PMID/DOI
  (reuse `references._parse_source`). No citation, or no resolvable PMID/DOI → flag as `[uncited]` /
  unverified, and surface the PubMed/DOI link for the human to confirm.
- **Id collision:** an `id` that matches an existing compound → flag *"id already exists; importing
  overwrites it"* and require an explicit confirm. Never silently clobber curated data (bufalin /
  ursolic acid).

**Two-way, like the importance gate.** Structural hard-fails block the write (you cannot build the
molecule). Soft-flags are shown; the chemist **acknowledges** (the same override-with-recorded-reason
pattern as the high-importance gate) and may still import — but the flags travel with the record
(unverified citations stay tagged `[uncited]`; they are not silently promoted to cited). The gate
**never fabricates and never auto-fills** a citation. In the MVP the gate checks that an *identifier
is present and well-formed* and links out; it does **not** call NCBI to verify author/title (a live
PMID→title check is a named future add).

---

## 3. The prompt builder — pure Python

Emits two artifacts. No model call; just template strings.

### 3a. One-time Claude Science project setup (permanent — review the wording carefully)

Pasted once into a Claude Science project's settings. **Draft for Luke's sign-off** (this is durable):

- **Project name:** `Chansu Compound Grounding`
- **Project description:**
  > Extraction of grounded, citation-backed structured records for medicinal-chemistry compounds,
  > for import into Chansu (a generic compound-modification tool). For a named natural compound with
  > known therapeutic activity, produce its molecular targets, druggability liabilities,
  > activity-essential regions, and modifiable handles, each backed by a real, PubMed-verifiable
  > citation. Never fabricate a citation, a structure, or a number. Where a fact cannot be grounded,
  > leave it empty and say so.
- **Agent context:**
  > You extract structured compound records for Chansu, a medicinal-chemistry tool with a strict
  > trust boundary: literature is grounded and cited; structures and properties are computed
  > deterministically downstream; every claim is provenance-tagged. Your job is the literature
  > grounding only.
  >
  > For the compound you are given, identify its molecular target(s) and role; its druggability
  > liabilities (for example toxicity, poor solubility, rapid clearance, poor selectivity); the
  > regions essential for activity, graded high / medium / low; and the positions that are reasonable
  > medicinal-chemistry handles to modify. Back every target, liability, and importance claim with a
  > real citation carrying a PMID and/or DOI that resolves on PubMed. Prefer primary literature. Do
  > not invent authors, years, identifiers, or numbers; if you are unsure a citation is real, omit
  > it. Provide a canonical SMILES from a named source (for example PubChem, with the CID), not from
  > memory. Do not predict binding affinity, toxicity, or efficacy, and do not claim a liability is
  > solved: you ground facts; the tool reasons and computes. Where a field cannot be grounded, leave
  > it empty and note what is missing. An honest gap is correct; a fabricated fill is a failure.

### 3b. Per-compound review prompt

Built from one input (`compound name`, plus optional identifiers / a target liability). The schema
and the runtime-derived controlled vocabulary are baked in, so the output comes back in-format:

> Produce a Chansu compound record for **{COMPOUND}**. Ground and return, each with a real PMID/DOI
> citation: a canonical SMILES with its source (e.g. PubChem CID) and InChIKey if available; molecular
> targets (name + role); druggability liabilities (kind + detail); activity-essential regions graded
> high / medium / low, each with a reason and a locator SMARTS; and modifiable positions (label +
> attachment type + locator SMARTS). Emit exactly this JSON, filling every field you can ground and
> listing anything you cannot under `"gaps"`: `{SCHEMA}`. Use the controlled vocabulary `{VOCAB}` for
> attachment types and liability kinds where it fits. Real citations only, verifiable on PubMed; no
> invented authors, years, or numbers; SMILES from a named source, not memory; do not predict
> binding, toxicity, or efficacy. If a fact cannot be grounded, leave it empty and say so.

**Known friction (called out honestly):** authoring correct **locator SMARTS** is the hardest ask for
Claude Science and the most error-prone field. That is exactly why importance/positions are
best-effort (§1) and why the gate resolves every locator on the real molecule (§2) — a bad SMARTS
surfaces as a visible flag, and the chemist fixes it, rather than corrupting the import.

---

## 4. The Ingest page — `chansu/ui/ingest.py`

A new tab, **"Add compound"**, alongside Workspace / Design memo / Sources. (The existing tabs act on
the *selected* compound; adding a *new* one is a different workflow and earns its own page.) Three
sections, all built to the chansu-design system (`.cs-*` classes, three type registers, §7 states,
§8 voice — no em dashes, no AI lexis). Runs `chansu-theme-review` before commit.

- **Section 1 — Prompt builder.** A Sans input for the compound name (optional liability focus). On
  submit, render the per-compound prompt and the project-setup block in mono code blocks (machine
  chrome), each with a Copy control (brass = interaction). Eyebrow labels (`.cs-eyebrow`).
- **Section 2 — Paste / upload the record (Producer A, the priority).** A text area (paste JSON or
  markdown) plus a file uploader; a **Validate** button (brass). The gate report renders in the
  design language: `pass` → quiet `.cs-pass`; structural fails → `.cs-flagcard` + `.cs-flag`
  (`--high`); soft/unverified → calm `.cs-declined` (never the flag register); each citation as a
  `.cs-cite` mono line + a `.cs-prov` tag (`lit` / `uncited`) + a PubMed/DOI link; SMILES/identifiers
  in mono; formulae and names via `formula()` / `chem()`. On pass (or acknowledged flags) an **Import**
  button writes the file; a `.cs-pass` confirms and the compound appears in the selector.
- **Section 3 — Research-log structuring (Producer B, wired-but-later).** Present as an architected
  placeholder until the model layer lands: a raw-log text area, a model picker (from the multi-model
  feature), a **Structure with model** action, the drafted **partial** record with an honest
  `.cs-declined` "not reachable" list, and a corner **"Uncertain? Hand it to Claude Science"**
  copy-prompt. Its output flows into Section 2's gate — B never bypasses the gate.

---

## 5. Storage and integration

- **Write** the validated record to `data/compounds/<id>.json`. It appears in the sidebar selector
  automatically via the existing 60s-TTL glob (`chansu/ui/state.py:available_compound_ids`) — the §5
  acceptance test, live, with no restart.
- **Provenance on the record.** Stamp `annotations.source` (e.g. `"claude-science-import"` /
  `"research-log:model"`) so curated vs. imported compounds are distinguishable, and the memo's
  data-provided notes stay honest.
- **Git nuance (decision for Luke).** Writing into `data/compounds/` makes imports working-tree files
  (like `ursolic_acid.json`). For the demo that is fine. If we would rather keep demo imports out of
  git, add a `data/compounds/imported/` subfolder to the selector glob and gitignore it — a small,
  deferrable change. **Default: write to `data/compounds/`.**

---

## 6. Producer B — architected-for (built after the model layer)

The flow that turns a messy research log (your bufalin origin story) into a record:

- Uses the **same multi-model layer** as the reasoning page (default Claude; others pluggable). No new
  model interface.
- Produces a **partial** record: confidently-mapped fields fill in; anything the model cannot ground
  is **left empty and printed** as "not reachable — needs you / Claude Science." **Uncertain → deny,
  never guess.** This is the §6 rule and it mirrors the reasoning-checks panel.
- Every B-produced citation is tagged **unverified** until confirmed. The recommended fix is the
  corner copy-prompt: hand the log (or just the gaps) to Claude Science, whose grounded output
  re-enters via Producer A. B and A form a loop with Claude Science as the authoritative verifier —
  no misinterpretation survives two passes plus the deterministic gate.
- B's output **always** passes through the §2 gate; it is a drafting aid, not a second ingest path.

---

## 7. Trust boundary and design compliance

- **Pure-Python line.** Builder + gate: deterministic, no model. Models only in Producer B and the
  reasoning page.
- **§5 (generic engine).** `ingest.py` and the UI operate on generic field names (targets /
  liabilities / importance / positions) and derive vocabulary from data. No compound-specific token
  enters `chansu/` — including the prompt template text and code comments. `tests/test_core.py`
  stays green.
- **§6 (trust boundary).** The gate never fabricates or auto-verifies a citation; unverified stays
  `[uncited]`; honest-failure and decline states use `.cs-declined`, never the flag/error register.
- **Voice + classes.** §8 register throughout; reuse the `.cs-*` contract, add classes if needed,
  never repurpose.

---

## 8. Test fixtures and demo plan (noted, not built now)

- **batrachotoxin** — Luke's real raw research log; the **Producer B** test fixture once B exists.
  A toxin, but ingestion is deterministic (no reasoning), so ingesting its data is fine.
- **epibatidine** — Luke's intended **prompt-builder** demo compound. Also a toxin. It has a strong
  on-thesis story (its own history is "potent toxin → non-toxic analgesic analog"), but for a
  life-sciences demo the optics favor a benign compound.
  - **Safer suggestion (recommended): curcumin** — natural, well-known activity, textbook druggability
    liabilities (poor solubility, rapid metabolism, low bioavailability), heavily cited, obvious
    prodrug/formulation avenues. Lets the **full** pipeline (including reasoning) run clean end-to-end.
  - **Alternative: artemisinin** — natural product with a celebrated derivatization success
    (artesunate/artemether fixed its PK). Great narrative, benign.
  - **Framing:** use a benign compound (curcumin) to show the happy path end-to-end; keep a toxin
    (epibatidine / batrachotoxin) to demonstrate the honest-decline + deterministic-floor behavior.
    Both have demo value, for different stories.

---

## 9. Build sequence (Path A)

1. **Contract + vocabulary derivation** — formalize the record; a helper that derives the controlled
   vocabulary from the loaded strategy library.
2. **`chansu/ingest.py`** — `validate_record` + `IngestReport`/`Check`; reuse `compound_from_dict`
   validation and `references._parse_source`. Pure, unit-tested.
3. **Prompt builder** — `build_review_prompt(name, ...)` + the project-setup constants (§3).
4. **Write path** — `write_record(report) -> Path` into `data/compounds/`, with `annotations.source`.
5. **`chansu/ui/ingest.py` + wire the tab** into `chansu/ui/app.py`; build to chansu-design; run
   chansu-theme-review.
6. **Tests** (`tests/test_ingest.py`) — valid record passes; invalid SMILES hard-fails; unresolvable
   locator flags; uncited citation flags; vocab lint warns; write + reload round-trips. `test_core`
   generic rule stays green.

Each step is independently checkable (the project's evidence-before-assertions cadence).

---

## 10. Out of scope (this pass)

- Producer B full build (phase 3 — needs the multi-model layer).
- Hosted MCP connector (phase 4 — "coming soon" surface).
- Live NCBI author/title verification (future add on top of the identifier check).
- Any model inside the builder or the gate.
- Binding-affinity / toxicity / efficacy prediction (PROJECT.md §14).

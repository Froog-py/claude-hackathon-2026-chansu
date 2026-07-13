# Design — Day 5 Streamlit UI (molecule viewer · design memo · reference workspace)

**Date:** 2026-07-12 · **Status:** approved (brainstormed with Luke), implementing · **Not committed** (Luke commits).

## Problem & value thesis
The engine is complete and 49 tests green: a compound loads *from data*, the deterministic pipeline
grounds it (cited targets / liabilities / importance map), matches precedent strategies, generates
RDKit-validated + gated + scored analogs, and the reasoning layer adds a best-effort Claude rationale
that degrades honestly (the reasoning-checks panel; §6). All of this is reachable only through
`python -m chansu.cli`. Day 5 gives it a **usable multi-screen interface** and hardens the bufalin demo.

**The architecture's thesis, which the UI must make legible:** the **deterministic design + cited
literature is immediately useful to a working chemist on its own** — they can read the grounded
molecule, the importance map, the precedent-backed avenues, and the scored analogs without any model
call. **Claude reasoning is a bonus that runs on top and degrades honestly** — even when its own
safety layer declines (the bufalin case), the app loses nothing of substance. The UI is built so the
deterministic floor renders instantly and offline; the model is always optional.

## Goals / non-goals
**Goals.** A focused 3-screen Streamlit app over the existing core: (1) a strong molecule **Workspace**
with RDKit 2D rendering, a MolView-style multi-representation 3D viewer, and substructure highlighting
of the importance map; (2) a **Design memo** screen showing the full provenance-tagged output incl. the
reasoning-checks transparency panel; (3) a **Sources / Reference** workspace that organizes the existing
citations Zotero-style. Harden bufalin across its liabilities; rehearse the honest-failure and
reasoning-declined moments.

**Non-goals (this week).** No multi-user auth / accounts / persistence (§14). No editable/persisted
reference tags this week (read + auto-organize only; user-tagging is a labeled stretch). No compound
knowledge in engine code (§5) — the UI adds none. No new prediction of binding/tox/efficacy (§6, §14).
No hand-built React (Streamlit + escape hatch only, §11). Visual styling (dark theme, custom CSS) is a
**separate later pass** — this spec is function-first and deliberately ignores look-and-feel.

## Architecture & layering (PROJECT.md §10)
The core stays framework-agnostic; the UI composes it and never buries chemistry in Streamlit code
(Luke's explicit requirement). Three new framework-agnostic units + one thin UI package:

| Unit | Kind | Depends on | Tested without Streamlit |
| --- | --- | --- | --- |
| `chansu/core/generation.py::region_match_atoms` | core, generic | RDKit | yes |
| `chansu/render_mol.py` (`draw_molecule_svg`, `molblock_3d`) | render helper (sibling to `report.py`) | RDKit | yes |
| `chansu/references.py` (`Reference`, `build_reference_index`) | aggregation over core `Citation`s | core models | yes |
| `chansu/ui/app.py`, `chansu/ui/viewer.py` | interface (Streamlit) | streamlit, py3Dmol, the above | verified in browser |

`import chansu.core …` never imports streamlit or py3Dmol. The generic helpers use only RDKit (already a
dependency), so the 49 existing tests and the core stay dependency-clean; only the `chansu/ui/` package
needs the UI libraries.

---

## Screen 1 — Workspace (the hub)
The "here is the molecule and what matters, all cited" screen. Sections:

1. **Identity** — name, id, canonical SMILES, InChIKey, structure source (e.g. `PubChem CID 9547215`),
   class annotation. Rendered from `Compound` fields (mirrors `report._identity_lines`), each database
   fact plainly labeled.
2. **Molecule viewer** — the star feature; see the dedicated section below.
3. **Grounding** — Targets, Liabilities, and the graded Importance map, each item carrying its
   provenance tag (`[literature — cited]` with the source, or an honest uncited tag), reusing the same
   provenance vocabulary as `report.py`. Importance regions show `[HIGH|MEDIUM|LOW] label — reason` and
   colour-key-match the viewer highlight.

## Screen 2 — Design memo
Primary render is the **faithful text artifact** produced by the existing, already-tested
`render_memo(compound, mol, result, reasoning)` — shown in a monospace block. This gives us the exact
provenance-tagged memo (scoring rubric, per-liability candidates with score + property deltas + gate
flags, honest-failure liabilities, the reasoning-checks panel, the design synthesis) with **zero logic
duplication** and full fidelity to the CLI. Rationale: lowest-risk, fully honest, and every claim already
carries its provenance tag.

Two structured flourishes read from the *same* data (no duplicated logic), included as staged niceties:
- **Reasoning-checks status list** (above the text): one green/red row per `DesignReasoning.checks`
  entry — `label · passed | declined (refusal/bio)`. This is the live trust-boundary showcase, so it is
  worth a structured widget even though it also appears in the text memo.
- **Per-analog 2D structure** (staged, build-if-time): each valid candidate's analog drawn from its
  `product_smiles` via `draw_molecule_svg`, beside its score/deltas.

The memo screen is a strong candidate for full structured re-rendering at the later styling pass; for
Day 5 it leads with the faithful text so it is correct and done.

## Screen 3 — Sources / Reference (Zotero-style, read + auto-organize)
Organizes the citations that **already exist** in the data — no new authoring, no compound knowledge in
the engine (§5). Backed by `build_reference_index` (below).

- **Controls:** *Group by* — Subject · Role · Source-type · Flat list; *Sort by* — citation name ·
  number of claims backed.
- **Folders:** one group header per group value. A paper backing several subjects legitimately appears in
  several folders (Zotero-like), which is correct, not a bug.
- **Card per paper:** the full formatted citation (name), link chips (PubMed and/or DOI), and tag chips
  (the roles it backs: `target` · `liability` · `importance` · `strategy-precedent`).
- **Expander (the "detailed if needed"):** full citation string, PMID + DOI as explicit links, the exact
  list of claims it backs (e.g. `target: Na⁺/K⁺-ATPase`, `liability: systemic_toxicity`,
  `importance: C14 tertiary hydroxyl`), and any `Citation.note`. This surfaces the extract-once /
  reuse-many trail (§9).

## Two-way gate — live seam (PROJECT.md non-negotiable #4)
The two-way gate is a non-negotiable, and §13 already names "the warhead-edit flag as the two-way-gate
moment." Rendering `render_memo` alone shows the gate only as a **historical record** — a flag buried in
the monospace block, visually identical to mundane "no encoded transformation" flags, with the override
half absent (the CLI path never calls `.override()`). This screen surfaces the gate as an **act**.

**Feasible because the gate is already clean and standalone** — no entanglement, no duplication, no
compound knowledge added to the engine. The seam calls three existing pure functions:
`resolve_position(mol, locator)` → `importance_gate_flags(compound, mol, atom_idx)` → `Flag.override(reason)`.

**Flow (on the Workspace tab, beside the viewer):**
1. A **selectbox of `compound.modifiable_positions`** (data-driven; §5-safe). For bufalin these are
   **C3 secondary hydroxyl** (benign) and **C14 tertiary hydroxyl** (high-importance) — the "one benign,
   one flagged" contrast falls out of the data for free, no pre-defined UI content.
2. **"Check this edit"** → `resolve_position` locates the atom; `importance_gate_flags` returns live flags.
   - **Pass:** "No high-importance conflict — this position is not in a flagged region" (green).
   - **Flagged:** the `high_importance_region` flag rendered structured — message, region reason, and its
     `[literature — cited]` citation (red/amber), *not* buried.
3. If flagged, a **text input + "Record override"** → `Flag.override(reason)` (raises on an empty reason;
   caught → "a reason is required"). On success: "Overridden by chemist. Reason recorded: …", held in
   `session_state` keyed by `(compound_id, position_id)`.
4. *Optional enhancement:* highlight the chosen position's atom on the 2D viewer while checking.

**Honest scope bound:** this demonstrates the **high-importance-edit** half of the gate (the canonical
"warhead" moment, §13). The invalid-structure half lives in generation's RDKit sanitization and is not
cleanly drivable live without generating — the seam does not claim to cover it.

**Staging:** **not** must-ship. Build order is viewer (2D floor) → memo → references → *then* this seam.
Estimate ~1.5–2.5 h, all Streamlit glue, zero engine code. Fallback if time compresses: a **structured
callout** (~30–45 min) that lifts the existing `code == "high_importance_region"` flags off
`result.candidates` into a widget so the flag is at least *visible* — shipped honestly as "recorded," not
claimed as an act.

## About modal & branding
- **About** — an `@st.dialog` modal opened from an "About" button in the header/sidebar: a short project
  description (what Chansu is, the med-chem hypothesis-generation use case, that it was built for the
  *Built with Claude: Life Sciences* hackathon), plus links to the GitHub repo
  (`https://github.com/Froog-py/claude-hackathon-2026-chansu`) and Luke's LinkedIn
  (`https://www.linkedin.com/in/luke-kerner-25fus/`). ~20–30 min; staged nicety, not must-ship.
- **Logo** — `logo-chansu.png` in the app header / sidebar. Sizing revisited at the styling pass.

---

## The molecule viewer (the priority feature)
MolView-style: a 2D Lewis panel **and** an interactive 3D viewer with multiple representations, plus a
toggleable importance-map overlay. **Two rendering engines**, because ball-and-stick / space-filling /
licorice are inherently 3D and do not come from RDKit's 2D drawing.

### Controls
- **Representation** (single selector): `2D — Lewis structure`, `3D — stick (licorice)`,
  `3D — ball & stick`, `3D — space-filling (CPK)`, `3D — wireframe`.
- **Highlight importance map** (toggle, default **on**) — the importance overlay only. Independent of the
  always-on element colouring.
- **Colour key** (legend) — high = red, medium = amber, low = blue, each swatch tied to its regions'
  cited reasons. Distinct in grayscale (different luminance) for colour-blind readability. Exact hex
  values finalised at the styling pass.

### Two independent colour layers (as Luke split them)
- **Element colouring** — O red, N blue, C grey, H white — **always on**; it is how a chemist reads a
  structure. Never toggled.
- **Importance-map overlay** — high/medium/low colours over the mapped regions — **the toggle**. On:
  regions are haloed (2D) / recoloured (3D). Off: pure element colouring, no overlay.

### Engine / robustness decisions
- **py3Dmol driven directly**, its self-contained HTML embedded via
  `streamlit.components.v1.html(view._make_html(), height=…)`. **`stmol` is deliberately not used** — it
  has a history of breaking against Streamlit version bumps; going direct removes that failure mode.
- **Honest caveat:** py3Dmol's HTML loads 3Dmol.js from a CDN inside the frame, so the **3D view needs
  internet** at demo time; the **2D view is fully offline**. Flagged for the styling pass if we choose to
  bundle 3Dmol.js locally.
- **3D coordinates:** `molblock_3d(mol)` runs `AddHs → EmbedMolecule (ETKDG) → MMFFOptimizeMolecule
  (best-effort) → MolToMolBlock`. `AddHs` appends H atoms after the heavy atoms, so **heavy-atom indices
  are preserved** — the importance atom indices computed on the no-H mol stay valid for 3D highlighting.
  Returns `None` on embed failure → the viewer falls back to 2D with a plain note (describe-don't-break).

### Interaction (rotate / zoom / pan)
Interactive manipulation is a **3D capability and comes for free with py3Dmol** — drag to rotate, scroll
to zoom, right-drag to pan, natively in the embedded 3Dmol.js canvas. No extra work beyond the Phase-2 3D
build. The **2D Lewis structure is static** by nature: "rotate" is not meaningful for a flat drawing, and
zoom/pan on the SVG is an optional small later add (an svg-pan-zoom helper), not a requirement. So the
interactive rotate/zoom the demo wants *is* the 3D viewer.

### Build staging (submission is tomorrow)
1. **2D floor first** — Lewis structure + importance highlighting + toggle + legend. Fully offline,
   low-risk, satisfies §13's substructure-highlighting requirement. Build and **verify in the browser**
   before touching 3D.
2. **3D second** — py3Dmol multi-style viewer + importance overlay in 3D. Built on top; if it gets hairy,
   Phase 1 already ships the requirement.

---

## Data flow & caching
Streamlit re-runs the whole script on every interaction, so the fast/pure half and the slow/refusing
half are handled differently.

- **Deterministic design — cached, keyed on `compound_id` (a string).**
  `get_design(compound_id)` returns `(compound, result)` via `@st.cache_data`; `DesignResult` and
  `Compound` are plain, picklable dataclasses. The `Mol` is **recomputed per run** with
  `to_mol(compound)` (cheap `MolFromSmiles`) rather than cached, avoiding any Mol-pickling question.
  `load_strategies()` is cached the same way. This renders Workspace, the memo skeleton, and references
  instantly, with **zero network**.
- **Claude reasoning — gated behind an explicit button, stored in `session_state`.**
  A **"Run Claude reasoning"** button calls `reason_over_design(compound, result, model, depth)` inside a
  spinner and stores the `DesignReasoning` under `session_state["reasoning:{compound_id}:{depth}"]`. It
  is **not** re-run on unrelated reruns. The deterministic memo renders with or without it; when present,
  the rationales, synthesis, and reasoning-checks panel layer in. This is the trust-boundary demo: show
  the complete deterministic memo (the floor), click, watch the checks panel report "1 of 6 passed; 5
  declined by the model's own safety layer (bio)."
- **Depth toggle** — a small radio (`Strategy-level` default / `Compound-specific`), mirroring the CLI
  `--depth`. Changing depth does not auto-run; the button does. Lets us demo Mode A vs the B→A fallback.
- **Reasoning model** — one `ClaudeReasoningModel(effort="medium")` via `@st.cache_resource`.
  Construction reads no credentials; a missing key/backend surfaces only when the button is pressed, and
  `reason_over_design` already catches `ReasoningError` and returns `available=False` (no crash).
- **Compound selector (sidebar)** — lists the ids found in `data/compounds/*.json` (default from
  `load_config()["demo_compound"]` = bufalin). When Luke drops in the clean second compound (data only,
  §5), it appears automatically — a live demonstration of the acceptance test.

---

## New modules & signatures

```python
# chansu/core/generation.py  (beside resolve_position — generic, no compound knowledge)
def region_match_atoms(mol: Mol, locator: StructureLocator) -> list[int]:
    """All atom indices of the locator's first SMARTS match — the whole region, for highlighting.
    Uses matches[0] (the same deterministic match resolve_position anchors to), so 2D/3D highlighting
    stays consistent with the gate/position logic. [] when the SMARTS is invalid or does not match."""
```

```python
# chansu/render_mol.py  (new; sibling to report.py; framework-agnostic; RDKit only)
def draw_molecule_svg(
    mol: Mol,
    highlight_atoms: Optional[dict[int, tuple[float, float, float]]] = None,  # atom idx -> RGB (0..1)
    size: tuple[int, int] = (520, 400),
) -> str:
    """A crisp 2D Lewis-structure SVG via rdMolDraw2D.MolDraw2DSVG. Computes 2D coords
    (rdDepictor) if the mol has none. When highlight_atoms is given, passes highlightAtoms +
    highlightAtomColors (and the bonds internal to each highlighted set) so the importance overlay
    reads as region halos over the always-on element colouring. Returns the SVG string."""

def molblock_3d(mol: Mol) -> Optional[str]:
    """3D MDL molblock: AddHs -> EmbedMolecule(ETKDG) -> MMFFOptimizeMolecule (best-effort) ->
    MolToMolBlock. AddHs preserves heavy-atom indices (H appended last), so importance atom
    indices stay valid. None on embed failure (viewer falls back to 2D)."""
```

```python
# chansu/references.py  (new; aggregation over core Citations; no compound knowledge)
@dataclass
class Reference:
    key: str                       # dedupe key: DOI, else PMID, else the citation label
    citation: str                  # the full formatted citation string (Citation.label)
    pmid: Optional[str]
    doi: Optional[str]
    urls: list[str]                # pubmed and/or doi.org links, derived from source
    roles: list[str]               # {"target","liability","importance","strategy-precedent"}, sorted
    subjects: list[str]            # what it grounds: target names, liability kinds, region labels, strategy ids
    backs: list[tuple[str, str]]   # (role, detail) per claim citing it — the expander's detail
    note: Optional[str]

def build_reference_index(compound: Compound, strategies: list[Strategy]) -> list[Reference]:
    """Walk every Citation on the compound (targets, liabilities, importance_map) and the strategy
    library; dedupe by DOI/PMID (parsed from Citation.source, e.g. 'PMID 20388710 | DOI 10.1074/...');
    aggregate roles/subjects/backs across the claims that share a paper; derive PubMed/DOI URLs.
    Generic — reads Citation objects wherever they hang, invents nothing."""
```

```python
# chansu/ui/app.py       — entry: sidebar (compound select, depth, Run-reasoning button) + 3 st.tabs
# chansu/ui/viewer.py    — render_viewer(compound, mol): representation selector, toggle, legend,
#                          2D (draw_molecule_svg) / 3D (molblock_3d + py3Dmol), importance overlay
```

**Run:** `.venv/bin/streamlit run chansu/ui/app.py` from the repo root. `app.py` prepends the repo root
to `sys.path` in a short documented bootstrap (Streamlit puts the *script's* dir on the path, not the
repo root, so `import chansu …` would otherwise fail — a common Streamlit footgun). `python -m chansu.cli`
is untouched.

---

## Error handling — honest degradation (matches the trust boundary)
- **Reasoning backend down / not clicked / no key** → deterministic memo renders fully; reasoning panel
  shows the existing `available=False` "not run" note. No crash (`reason_over_design` catches
  `ReasoningError`).
- **3D embed fails** (`molblock_3d` → None) → viewer falls back to the 2D Lewis view with a plain note.
- **A region's SMARTS does not match** (`region_match_atoms` → []) → that region simply is not
  highlighted; every other region and the structure still render.
- **3Dmol CDN unreachable** → the 3D frame is empty; the 2D view always works. Noted in-app.
- **Provenance is never lost:** every surface preserves the `[computed]` / `[literature — cited]` /
  `[reasoning — <model>]` / `[hypothesis]` tags verbatim (§6).

## Testing
Keep all 49 green; add unit tests for the **generic helpers only** (no Streamlit) — the app itself is
verified by running it and looking in the browser, since its logic lives in these tested helpers.

- `test_render_mol.py`
  - `region_match_atoms`: returns a non-empty set including `resolve_position`'s anchor for a known
    bufalin region; `[]` for a deliberately non-matching SMARTS.
  - `draw_molecule_svg`: returns a string containing `<svg`; passing `highlight_atoms` changes the
    output vs no-highlight; deterministic (same input → identical output).
  - `molblock_3d`: returns a molblock with a real 3D conformer (a non-zero z coordinate) for bufalin.
- `test_references.py`
  - `build_reference_index(bufalin, strategies)`: dedupes (unique papers < total citing claims); a
    paper cited by several claims (e.g. Katz 2010, on targets + importance) aggregates ≥2 `backs` and the
    right `roles`; URL derivation yields a `pubmed…/<PMID>` and a `doi.org/<DOI>` link; a strategy's
    precedent citation carries role `strategy-precedent`.

## Dependencies
`uv pip install --python .venv/bin/python streamlit py3Dmol`. UI-only; core and its tests do not import
them. (No `stmol`.)

## Risks & mitigations
- **3D viewer is the newest surface** → 2D-floor-first staging guarantees a working demo regardless; py3Dmol
  driven directly (no stmol) removes the most common breakage.
- **CDN dependency for 3D** → 2D is offline and satisfies §13; bundling 3Dmol.js is a known later option.
- **Streamlit rerun re-invoking the model** → button + session_state gating makes every model call explicit.
- **Scope creep on submission eve** → memo screen leads with the faithful, tested text artifact; per-analog
  drawings and structured memo rendering are explicitly staged "build-if-time," not required for done.

## Definition of done (Day 5)
The app runs start to finish smoothly: pick bufalin → Workspace shows the highlighted molecule (2D, and 3D
in at least one representation) with cited grounding → Design memo shows the full provenance-tagged output
→ clicking "Run Claude reasoning" populates the reasoning-checks panel (honestly reporting the bio
declines) → Sources organizes the citations Zotero-style. All 49 + new tests green. The validation story
is demonstrable on screen: the by-hand soft-drug design reproduced; the honest-failure liability; and —
**via the live gate seam** — proposing the C14 edit, seeing it flagged with its cited reason, and
recording an override (§4 as an act, not a buried record). Nothing committed until Luke reviews.

The **must-ship** subset of the above is: Workspace (2D viewer + highlighting + grounding), the Design
memo (faithful provenance-tagged text + reasoning-checks panel), and Sources. The 3D viewer, the live
gate seam, the About modal, and per-analog drawings are **staged enhancements** — each lands on top of a
demo that already works and tells the story.

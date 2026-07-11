# Chansu — Project Charter

> **Name: Chansu.** Chán sū (蟾酥) is the traditional preparation bufalin is derived from —
> the name honors the flagship compound while the tool itself stays compound-agnostic.
>
> This is the source of truth for **what** we're building and **why**. Read it at the start
> of every work session. Update it deliberately, never casually. If a task doesn't serve the
> scope below, it is out of scope for this week.

**Event:** Built with Claude: Life Sciences — global virtual hackathon, July 7–13, partnered
with the Gladstone Institutes.
**Track: Build.** ("Build beyond the bench: start from a user in the life sciences you can
name, and use Claude Code to create the tool they're missing — working software that outlasts
the week.")

---

## 1. One-line scope

An agentic tool that helps a chemist take a natural compound, pull together the literature on
it, understand which parts of the molecule matter and why, and generate **grounded,
citation-backed hypotheses** for how to modify it — adding molecular handles or swapping
groups to fix a liability (toxicity, poor distribution, poor solubility, rapid clearance,
weak potency, and so on). **Bufalin is the flagship demo compound. It appears only in the
data, never in the engine.**

Everything in this document serves that sentence.

## 2. The problem

Potent natural compounds — bufadienolides, cardiac glycosides, alkaloids, and other amphibian
and plant toxins — frequently have real therapeutic activity (anti-cancer, antiviral, and
more) but can't be used as drugs because of some liability: too toxic, too poorly distributed,
too insoluble, cleared too fast. Medicinal chemists fix these by borrowing structural
strategies from drugs that already solved the same problem. That work is done by hand, one
compound at a time, and takes heavy literature digging plus organic-chemistry judgment just to
reach a hypothesis worth testing.

## 3. Who it's for (the named user)

The **translational or medicinal chemist** sitting on a compound they know has activity but
can't yet use — who needs to explore modification ideas fast, grounded in real literature and
real precedent, and organized in one place. The tool is a thinking-and-organization partner
for generating and vetting modification hypotheses, not a replacement for their judgment.

## 4. What it does (functional — internal mechanisms deliberately open)

A chemist provides a compound (and optionally a target). The tool then:

1. **Resolves** the compound to a machine-readable structure.
2. **Gathers and grounds** the relevant literature — the target(s) and binding-site context,
   the compound's liabilities, its mechanisms — from a pluggable set of sources.
3. **Builds a graded importance map** of the molecule: which regions are high/medium/low
   importance to activity, and why, each tied to a citation.
4. **Identifies the liabilities** to address (any medicinal-chemistry deficiency, not only
   toxicity).
5. **Matches** each liability to precedent-backed strategies from the strategy library and
   reasons by analogy from real approved-drug precedent.
6. **Generates candidate analogs** — concrete, chemically-validated modifications at
   appropriate positions.
7. **Computes** deterministic properties for each candidate and similarity to the parent.
8. **Scores, ranks, and explains** candidates on a transparent rubric.
9. **Outputs** a provenance-tagged design memo the chemist can trace end to end.

The reasoning is powered by **Claude** (this is a Built with Claude project). Deterministic
computation is **RDKit**. Precedent lives in the **strategy library**. Literature grounding
runs through the **literature pipeline** (see §9). Keeping these jobs separate is the design.

---

## 5. The core principle — generic engine, compound-in-data

The single most important architectural rule:

> **No compound-specific knowledge may live in the engine.** Nothing about bufalin,
> bufadienolides, steroids, lactones, or Na+/K+-ATPase appears anywhere in the pipeline code.
> It all lives in **data** — a compound instance. Bufalin is instance #1.

**Why:** the pipeline (retrieve, map importance, identify liabilities, match strategies,
generate, compute, rank, memo) is the *code*; the compound is the *input*. This is what lets a
deep flagship demo coexist with a genuinely general tool. Bufalin gives us depth; the
abstraction gives us reach.

**Acceptance test (enforce this):** adding a new compound must require creating only new
**data** — a compound definition, its importance map, its liabilities, its literature — and
must **not** require editing engine or pipeline code. If engine code has to change to add a
compound, the abstraction has leaked and must be fixed. *(A thin second compound added this
way is the single most convincing stretch goal — it demonstrates generality instead of
claiming it.)*

---

## 6. The trust boundary (the soul of this project — non-negotiable)

The tool is **not an oracle and never pretends to be.** De novo prediction of binding,
toxicity, or efficacy is unsolved; a tool that fakes it collapses the moment a real scientist
uses it. Trust comes from *where the line is drawn* between the parts:

- **Claude (reasoning engine)** — reads and synthesizes literature, builds the importance map,
  identifies liabilities, matches strategies, reasons by analogy, writes the memo. Reliable
  **as retrieval and reasoning**, not as prediction.
- **RDKit (deterministic)** — computes structural properties (logP, TPSA, MW, H-bond
  donors/acceptors, rotatable bonds, Lipinski/Veber flags), Tanimoto similarity to parent,
  synthetic-accessibility score, and validates every generated structure. **Math, not
  opinion.**
- **Strategy library (human-authored, precedent-backed)** — each entry is a documented
  strategy plus its mechanism, its precedent drug, and a citation. The agent **matches to this
  set; it never invents mechanisms.**

**Every claim the tool emits carries a provenance tag:**
`[computed]` · `[literature — cited]` · `[hypothesis — needs wet-lab validation]` ·
`[out of scope — e.g. formulation/delivery]`.

**The two-way gate.** The tool never silently blocks *or* silently allows. When a generated
structure is chemically invalid, or a modification lands on a high-importance region, the tool
**flags it with the reason** — but the chemist can **dismiss/override** ("you're flagging a
change I intend"), and the override is recorded. It surfaces concerns; the human decides.

**Honest failure is a feature.** When nothing matches cleanly (an exotic compound, an
unfamiliar liability), the tool says *"no well-precedented strategy applies here"* rather than
inventing one. Demonstrating the tool **declining to over-claim** is more convincing to real
scientists than any success case.

**Non-goals.** It does not predict binding affinity, does not predict whether an analog
"works," does not claim a liability is solved. It generates grounded hypotheses and organizes
evidence so a chemist can decide.

---

## 7. The data model (the generic spine)

Each item is a **role**, not a chemical. A compound is a fully-populated set of these.

- **Compound** — a structure; its class is annotation, not logic.
- **Target(s)** — a compound may have **multiple targets** (bufalin hits Na+/K+-ATPase, ABCB1,
  and apoptosis pathways). The tool scans literature across all of them.
- **Importance map** — a **graded, advisory** annotation of regions as high/medium/low
  importance to activity, each with a reason and citation. **Not** a binary "must not touch."
  Modifying a high-importance region is **flagged, not forbidden** — sometimes it's the
  intended move (tuning the warhead to bind better; the C3 sugar shifting isoform selectivity).
  *For the flagship, this map is **curated from the literature** (it's in the research log),
  not computed. General auto-detection of pharmacophores is a research problem and is out of
  scope this week.*
- **Modifiable positions** — sites where handles can attach, with AI-suggested rationale.
- **Liability** — **any** medicinal-chemistry deficiency: toxicity, poor distribution / barrier
  crossing, poor solubility, rapid clearance, insufficient potency, size, etc. A compound can
  have several.
- **Strategy** — a precedent-backed fix for a **class** of liability, tagged with the liability
  types and attachment-point types it applies to. Each entry: the modification concept · the
  mechanism · the **precedent approved drug** · a **citation** · the liability class it
  addresses. (Because strategies key on liability/attachment *type*, the library is reusable
  across compounds — this is the moat.)
- **Literature source** — pluggable (see §9).

**Precedents vs. targets — a hard distinction.** Fluticasone propionate (kills systemic
exposure via a self-inactivating group) and Levodopa (crosses the blood-brain barrier as a
prodrug, then converts in situ) are **precedents** — reference examples the tool reasons
*from*, spanning different liability classes. They are **never** compounds the tool redesigns.
Precedents are citations in the strategy library; they are not inputs.

---

## 8. Analog generation (the hardest part — treat with care)

This is the **#1 technical risk.** Computing properties and drawing structures are solved;
*programmatically editing a molecule* into a valid new structure is fiddly and error-prone, and
a naive approach produces chemical garbage. Design:

- **Encoded transformations.** Generation is constrained to a small set of encoded reaction
  templates (Reaction SMARTS / RWMol editing) tied to strategy-library entries, applied only
  at identified positions. No free-form molecule invention.
- **Validate everything.** Every generated structure is RDKit-sanitized before it is shown or
  scored. Invalid structures never reach the user unflagged.
- **Two-way gate + override** (see §6): flag invalid or high-importance-region edits; let the
  chemist dismiss with the reason recorded.
- **Describe-don't-break fallback.** If a transformation can't be generated cleanly, the tool
  **describes** the modification in words and **highlights the position** rather than emitting
  a broken molecule.
- **Spike this first.** Build the simplest end-to-end generation proof-of-concept before
  building outward. If the project is going to hurt, it hurts here — surface it early.

---

## 9. The literature pipeline (grounding without drowning in context)

Papers are bloated; feeding whole PDFs into context repeatedly is unworkable. The pattern is
**extract-once, reuse-many**:

- When a paper enters the system, a **lightweight extraction pass** pulls only the structured
  facts we care about — binding-site claims, importance/pharmacophore claims, liabilities,
  mechanisms, the citation — and writes a **compact structured record** (a "distilled note").
- The reasoning agent reads the **distilled records**, not the raw PDFs. Each paper is
  processed once.
- **Multi-agent extraction** (small agents pick through individual papers; a coordinating
  agent synthesizes) is the validated pattern for this. **Gate the complexity:** build the
  single-pass extractor first; add a multi-agent split only if a single pass chokes on volume.

**The Reference tab (built-in — a core feature, not a stretch).** A workspace of **links,
citations, and the chemist's own notes** (exactly like the research log), stored in the app's
own database, that **the AI can read and write** (it can add its own distilled notes back).
Documents need not be downloadable — links and citations are fine. Import populates it; the
optional agentic-search-to-approve flow can populate it too (see §15). This replaces any
external reference-manager integration — it's cleaner, fully in our control, and it *is* the
answer to "how do we ingest literature."

**Claude Science (literature-analysis engine — component, not platform).** We stay Build track
and build the app in Streamlit, but use Claude Science where it is strongest: heavy paper
extraction, grounding, and citation-checking behind the app. *(Confirm the exact connector and
feature set from within Claude Science directly — the user is signed in on macOS. Treat
specific capability claims as "verify before relying," not settled.)* Using it authentically
also answers the submission's "how did you use Claude Science?" question.

---

## 10. Architecture — stratified layers (this is what enables everything future)

Build as clean, independent layers so each can evolve or be swapped without touching the
others. This stratification is what lets MCP, model-plugging, alternate front-ends, and new
data sources be **added on later without a rewrite.**

1. **Core library** — pure Python, framework-agnostic. The generic data model + deterministic
   logic (RDKit, generation, scoring). Knows nothing about UI, models, or how it's called.
2. **Reasoning / agent layer — pluggable.** Claude (Opus) drives it this week, behind a clean
   **model-adapter interface** so other models/agents (Codex, local, open-source) can be
   swapped in later. *Architected now; multi-model support is a stretch, not this week.*
3. **Service layer — MCP surface.** The core's functions are structured so they can be exposed
   over **MCP**, letting any external agent (Claude Code, Claude Desktop, a local model) drive
   the tool. Two-directional: the tool can *use* a model, and a model can *use* the tool.
   *Architected now; building the MCP server is a stretch.*
4. **Interface layer** — the Streamlit skin (see §11). Swappable; a future multi-user
   front-end would be a different skin over the same core.
5. **Data / reference layer** — the built-in Reference DB + pluggable literature sources
   (curated flagship set, import, Claude Science, future connectors).

**Discipline:** we **architect** for layers 2–3 (clean interfaces, no leakage) but **build**
only what the must-ship needs. This week the Streamlit interface calls the core directly with
Claude as the engine. MCP and multi-model are designed-for, built-if-time.

---

## 11. The interface (Streamlit, multi-screen)

- **Streamlit over a clean core.** Fast, stays in Python with RDKit and the agent, and has a
  documented **escape hatch** (custom HTML/React components) if a feature ever needs it — so
  no lock-in. A future rebuild would replace only this thin layer.
- **Multi-page**, not one screen: **Workspace** (the hub — molecule center + literature),
  **Strategies**, **Analogs**, **Design memo**, **Sources/Reference**.
- **Molecule rendering via RDKit** — drawn from the verified structure (this *is* the
  ChemDraw-like feature; the picture is the actual molecule, reproducible, not a scraped
  image), with **substructure highlighting** for the importance map.
- **3D view** via `stmol`/`py3Dmol` (a published Streamlit component) — **stretch.**
- Interactivity: 2D/3D toggle, region highlighting, the override/dismiss controls.

---

## 12. Flagship & validation

**Bufalin** is the flagship, and it demonstrates the tool's **breadth on its own** — no second
compound required for the demo. The research log shows bufalin has anti-cancer *and* antiviral
activity, multiple targets, and multiple liability types (toxicity, solubility, clearance,
distribution). So the demo shows the tool generating ideas across **different liabilities of
the same compound.**

**Validation:** the localized/self-inactivating analog design the user worked out **by hand**
(undergrad project) is the ground truth. The tool should independently surface that same
reasoning, ground every step, flag what it can't know — and ideally propose an avenue the user
hadn't considered.

---

## 13. Definition of done (what the demo shows)

Feed the tool **bufalin**, and it:
1. Grounds the target(s), binding-site context, and liabilities in cited literature.
2. Shows the graded importance map with reasons and citations.
3. For a chosen liability, proposes precedent-backed strategy avenues (each **cited**).
4. Generates candidate analogs — **chemically valid**, with computed property shifts and
   similarity-to-parent showing the active region intact.
5. Flags what needs a wet lab; notes where a different class of solution (e.g. formulation)
   fits better; and **declines to over-claim** where nothing matches.
6. Reproduces the user's by-hand design on one avenue, and proposes a new one.
7. Returns a clean, provenance-tagged design memo.

A bounded, checkable, honest claim. That is the win.

---

## 14. NOT THIS WEEK (say no to these)

- Binding-affinity, toxicity, or efficacy **prediction** as a feature.
- **General/automatic** pharmacophore or importance detection (curate it for the flagship).
- Building the **MCP server** or **multi-model** support (architect for them; don't build).
- **Multi-user** auth, accounts, persistence, production hosting.
- A hand-built React front-end (Streamlit + escape hatch only).
- **Multi-agent** extraction orchestration unless single-pass demonstrably chokes.
- Implementing **formulation/delivery** (nanocarriers) — the tool *routes to it* as
  out-of-scope; it does not build it.
- Inventing strategies beyond the curated, cited library.
- Any wet-lab or experimental claim.

---

## 15. Open questions — decide as we go (propose options, don't silently pick)

- **Compound input** — SMILES-only vs. name→structure resolution. Flagship: bufalin's
  canonical SMILES from **PubChem** (not memory).
- **Extraction depth** — how much structure the distilled records capture; start minimal.
- **Agentic search-to-approve** — pointing an agent at a custom search prompt to gather
  candidate papers for the user to **approve** into the Reference tab. Desirable; **stretch**;
  design the approval gate honestly.
- **Claude Science surface** — exact connectors/capabilities to lean on (verify from inside).
- **Scoring rubric** — the transparent weighting for ranking candidates.

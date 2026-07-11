# Claude Code — Kickoff & Standing Instructions

> Give this to Claude Code to start the build. It bootstraps the repo and Day 1 and sets the
> standing rules for the whole week. `PROJECT.md` and `BUILD_PLAN.md` are the source of truth —
> this document tells you how to work within them.

---

## Context

We are building **Chansu**, a **Build-track** project for the *Built with
Claude: Life Sciences* hackathon. It is an agentic tool that helps a medicinal chemist take a
natural compound, ground it in the literature, understand which parts of the molecule matter,
and generate **grounded, citation-backed hypotheses** for modifying it to fix a liability
(toxicity, poor distribution, poor solubility, rapid clearance, weak potency, etc.). **Bufalin
is the flagship demo compound — in the data only, never in the engine.**

**Before doing anything, read `PROJECT.md` and `BUILD_PLAN.md` in full.** Do not proceed until
you have. They define the scope, the trust boundary, the data model, the architecture layers,
the day plan, and the explicit out-of-scope list.

---

## Standing rules (apply all week, every session)

1. **Scope is sacred.** Build only what's in `PROJECT.md`. If a task is not in scope, or is on
   the NOT-THIS-WEEK list, do not build it — flag it and move on. When in doubt, ask.

2. **The generic-engine rule.** No compound-specific knowledge in the engine — nothing about
   bufalin, bufadienolides, steroids, lactones, or Na+/K+-ATPase in the pipeline code. It all
   lives in data. **Acceptance test:** adding a compound must require only new data, never
   engine edits. If you'd have to edit engine code to add a compound, stop — the abstraction
   has leaked; fix it.

3. **The trust boundary is non-negotiable.** Claude reasons/retrieves; RDKit does the numbers
   and validates every structure; the curated library holds precedent. **Every output claim is
   provenance-tagged** (`[computed]` / `[literature — cited]` / `[hypothesis — needs wet-lab
   validation]` / `[out of scope]`). Never present a prediction as fact. **Never fabricate a
   citation.** Implement the **two-way gate**: flag invalid or high-importance-region edits, but
   let the user override with the reason recorded. Prefer **honest failure** ("no
   well-precedented strategy applies") over inventing one.

4. **Analog generation is the #1 risk — spike it first.** Before building outward, prove a tiny
   end-to-end path: apply one encoded transformation (Reaction SMARTS / RWMol) at one position
   on bufalin and get a **valid** structure back. Validate with RDKit sanitization. If a
   transformation can't generate cleanly, **describe and highlight** rather than emit a broken
   molecule.

5. **Architect the layers; build only what's needed.** Keep the core a clean, framework-agnostic
   Python library that knows nothing about the UI or which model calls it. Keep the reasoning
   layer behind a model-adapter interface, and structure core functions so they *could* be
   exposed over MCP later — but **do not build** the MCP server or multi-model support this week
   (they're stretch). Streamlit calls the core directly, with Claude as the engine.

6. **Manage context deliberately.** Papers are bloated. Use **extract-once, reuse-many**:
   distill each paper to a compact structured record and read the records, not raw PDFs. Save
   papers and records in the **reference-material folder** (below). Single-pass extraction
   first; only add multi-agent extraction if a single pass demonstrably chokes.

7. **Open questions get options, not guesses.** When you reach an undecided fork (see
   PROJECT.md §15), stop and propose 2–3 concrete options with tradeoffs. Don't silently pick.

8. **Naming & hygiene.** Distinctive repo and file names. Verify file contents before publishing
   or deploying anything.

9. **Ask, don't guess.** If something is unclear or load-bearing, stop and ask. Luke drives
   direction on genuine forks.

10. **Don't over-build.** Prefer the simplest thing that meets the day's objective. Deterministic
    core solid before layers.

---

## Division of labor

Claude Code writes **all** the code and makes implementation decisions. Specs and constraints
come from the planning docs, not pasted code. Other models (Codex 5.6, Grok) are used **only for
review** after a build — not for building. The build is Claude Code.

---

## Reference-material folder

Create a dedicated folder in the repo for reference material — the research log, saved papers
(links/PDFs), and the distilled structured records the extraction pipeline produces. The
literature pipeline reads from here. You own and maintain it.

---

## Repo & workflow

- **Project folder (already exists, contains these three planning docs):**
  `/Users/lukekerner/Projects/claude-hackathon-2026`
- **Create a new repo from this folder** under Luke's personal GitHub account (`Froog-py`).
  Distinctive name — `claude-hackathon-2026-chansu` (chosen with Luke). Public.
- **Branching:** `main` is the trunk. All work happens on **feature branches** off `main`,
  created via the **`/start` skill**. Do not commit work directly to `main`.

---

## Day 1 — do exactly this, in order, then report back

1. **Initialize the repo** at `/Users/lukekerner/Projects/claude-hackathon-2026` and create the
   new public GitHub repo under `Froog-py` (see Repo & workflow above). Commit the three
   planning docs to `main` **first**, then move to a feature branch via `/start` for the build
   work. Create the reference-material folder.
2. **Set up a Python environment with RDKit.** Smoke test: import RDKit and compute one property
   (e.g. molecular weight) on a known SMILES. Report the result.
3. **Get bufalin's canonical SMILES from PubChem** (state the CID and SMILES — do not use
   memory). Load it as compound instance #1 through a **generic compound data model** — no
   compound-specific engine code.
4. **Build the deterministic property module:** logP, TPSA, MW, H-bond donors, H-bond acceptors,
   rotatable bonds, Lipinski/Veber flags, Tanimoto similarity to a parent, synthetic-
   accessibility score.
5. **Generation spike:** apply one encoded transformation at one position on bufalin and validate
   the resulting structure with RDKit. Report whether it produced a clean, valid molecule.
6. **Minimal entry point:** running one command with bufalin as input prints its computed
   properties (and, if the spike worked, one validated analog).
7. **Produce the local-model handoff spec** (see below) — *after* the scaffold exists, not
   before.
8. **Stop and report:** what's working, the smoke-test result, bufalin's properties, and the
   outcome of the generation spike — before moving to Day 2.

---

## Deliverable: the local-model handoff spec (print this at the end of Day 1)

Luke is running a **separate Claude Code agent on a Windows PC** whose only job is to download,
set up, and integrate a **local model** as an alternate reasoning backend. That agent has no
context on this project. Once you have scaffolded the codebase and the reasoning layer's
**model-adapter interface** is defined (even in skeleton form), write out a **self-contained
instruction document** it can be handed directly.

Write the spec *from the real code*, not from assumptions. It must include:

- **What the system is**, in two or three sentences, and what the local model is expected to do
  in it (serve as a swappable reasoning backend behind the model-adapter interface).
- **The exact model-adapter interface** the local model must conform to: the call signature,
  the expected input/output shapes, how tool-calling (if any) is handled, and how errors and
  streaming are expected to behave.
- **The requirements the model must meet** to be usable here — e.g. capable enough for
  multi-step scientific reasoning over retrieved literature, a context window large enough for
  distilled records plus instructions, and tool/function-calling support if the adapter needs
  it. State the hard requirements plainly and let the PC agent choose a model that meets them
  and fits the hardware.
- **Hardware questions the PC agent must answer first** (available VRAM/RAM), since that
  determines which model sizes are even viable. Instruct it to check hardware *before* choosing.
- **How to serve it locally** and what endpoint shape the adapter expects.
- **How to verify the integration works** — a concrete smoke test against the adapter.
- An explicit note that this is a **stretch goal**: it must not modify or break the core, the
  Claude-backed path, or anything on the critical path. It plugs in behind the interface or it
  doesn't ship.

**Do not choose the specific local model yourself.** State the requirements and the hardware
constraints; let the PC agent select a model that satisfies them. Do not build the local-model
path into the main repo on the critical path — the adapter interface is the contract; the local
backend is optional and additive.

### Do NOT do on Day 1
- Do not build the reasoning agent, the literature pipeline, or any UI.
- Do not build the MCP server or multi-model support (stretch — architect only).
- Do not pick a literature-ingestion or extraction mechanism yet (that's Day 3).
- Do not add frameworks or persistence we haven't decided on.

---

## Notes on the ecosystem

- This is **Built with Claude**: the tool's reasoning (from Day 3) is powered by **Claude
  (Opus)**, and Claude Code is the build tool. Both matter for the submission.
- **Claude Science** will be used as a literature-analysis/extraction component from Day 3 —
  verify its exact connector/feature set from inside it before relying on specifics.
- The reasoning layer sits behind a **model-adapter interface** so other models can drive it
  later — but this week it runs on Claude.

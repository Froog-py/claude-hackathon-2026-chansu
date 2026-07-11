# DeRisk — Build Plan

> Companion to `PROJECT.md`. This is **how** and **when**. Read both at the start of every
> session. The governing principle below matters more than any single day's task list.

**Hard deadline:** Saturday, July 13, **9:00 PM** — *confirm the timezone with the organizers;
plan to submit with hours to spare, not minutes.*

**Reality:** starting midday July 8, one day behind kickoff. Fine — Day 0 is usually setup and
confusion anyway. We compress it into tonight.

---

## The governing principle

**The build finishes on Day 4. Days 5–6 are polish and submission, not building.**

Hackathons are lost by people still coding at 8:45 PM on deadline day. The enemy is not time —
it is scope. Deliberate on architecture; move fast by building *less*, not by thinking less.
Every day, protect the plan from good ideas that don't ship this week.

### The must-ship 80%

> **End of Day 4:** feed the tool bufalin → get a complete, provenance-tagged design memo with
> chemically-valid ranked analog candidates and their computed properties, grounded in cited
> literature, validated against the user's by-hand design.

Everything before Day 4 builds toward that. Everything after makes it presentable. Anything
labeled "stretch" exists only if the must-ship is already solid.

---

## Two things to spike on Day 1, before building outward

These are the two places the project can fail. Prove them small and early:

1. **Analog generation** (the #1 risk) — can we take bufalin's structure, apply an encoded
   transformation at a specified position, and get a **valid** new structure back that RDKit
   sanitizes cleanly? A tiny proof-of-concept answers this. If it's going to hurt, it hurts
   here.
2. **The generic data model** — is bufalin loaded as *data* with zero bufalin-specific code in
   the engine? Lock the abstraction before code accretes around a hard-coded compound.

---

## Day-by-day

### DAY 1 — July 8 (partial, today): Foundation + the two spikes
**Objective:** repo and docs live; deterministic core returns real numbers for bufalin; the
generation spike works; the data-model abstraction is locked.

- Fresh repo (distinctive name — see kickoff doc). Commit `PROJECT.md`, `BUILD_PLAN.md`, and
  `CLAUDE_CODE_KICKOFF.md` **first**, before code. Create the **reference-material folder**.
- Python env with RDKit; smoke test (import + one property on a known structure).
- Bufalin's canonical SMILES from **PubChem** (state the CID + SMILES used).
- Generic **compound data model** scaffold; load bufalin as instance #1 — no compound-specific
  engine code.
- Deterministic **property module**: logP, TPSA, MW, HBD, HBA, rotatable bonds, Lipinski/Veber
  flags, Tanimoto-to-parent, synthetic-accessibility score.
- **Generation spike**: one encoded transformation at one position → validate the result.
- Minimal entry point: bufalin in → properties out. **Report back before Day 2.**

*Do NOT build the reasoning agent, literature pipeline, or UI today.*

### DAY 2 — July 9: Strategy library + generation solidified
**Objective:** the precedent-backed library exists; generation is reliable across the library's
transformations.

- Author **5–6 strategy entries** across liability classes: soft-drug/antedrug inactivation
  (precedent: fluticasone); tumor-activated prodrug; targeting-ligand conjugation; PK-modifying
  edit; prodrug-for-distribution/barrier-crossing (precedent: Levodopa). Each entry: modification
  · mechanism · **precedent drug** · **citation** · liability class · attachment-point types.
- Harden the encoded transformations so each library strategy generates valid structures (or
  falls back to describe-and-highlight).

**Done when:** the library is precedent-backed and cited, and generation is reliable. *(Do not
fabricate citations. If a precedent set would help, Claude can supply real ones.)*

### DAY 3 — July 10: Literature pipeline + reasoning agent
**Objective:** the tool grounds itself in literature and reasons over it, provenance-tagged.

- **Reference tab + DB** (links, citations, notes; AI read/write). Load the research log as the
  flagship reference set.
- **Extract-once** pipeline: distill each paper to a compact structured record; agent reads the
  records, not raw PDFs. Single-pass first; multi-agent only if it chokes.
- Wire **Claude Science** as the extraction/grounding engine where it fits (verify surface).
- Reasoning agent: build the importance map, identify liabilities, match strategies — all
  cited and provenance-tagged.

**Done when:** given bufalin, the agent produces a grounded, cited importance map + liabilities
+ matched strategies.

### DAY 4 — July 11: Full loop — generate + gate + score + memo — **MUST-SHIP**
**Objective:** compound in, provenance-tagged design memo out.

- Analog generation across matched strategies → validated candidate structures.
- The **two-way gate**: flag invalid / high-importance edits; allow override with reason
  recorded.
- RDKit property engine on every candidate; similarity-to-parent; SA score.
- Transparent scoring/ranking; assemble the tagged memo.

**Done when:** feed bufalin, get the complete tagged memo with valid ranked candidates. **This
is the 80%. If nothing else ships, this must.**

### DAY 5 — July 12: Streamlit multi-screen UI + demo hardening
**Objective:** a usable multi-screen interface and an airtight bufalin demo.

- Streamlit multipage: Workspace · Strategies · Analogs · Design memo · Sources/Reference.
- RDKit structure rendering + substructure highlighting for the importance map.
- Harden the bufalin demo across **two or three different liabilities** to show breadth; make
  the memo clean and readable.
- Lock the validation narrative (by-hand design reproduced + a new avenue). Rehearse the
  honest-failure moment (tool declining to over-claim).

**Done when:** the demo runs start to finish smoothly and tells the validation story.

### DAY 6 — July 13 (ship by ~6–7 PM): Buffer + submission
**Objective:** submit with hours to spare.

- **Submission materials:** the ≤3-minute demo video, the project description, the public repo
  link. Draft the "how did you use Claude / Claude Science?" answer authentically (it's a
  required field). Team name (solo is fine).
- Final scope/honesty pass: every claim tagged, nothing overclaimed, limitations stated.
- **One** clearly-labeled stretch (below) only if the core is rock-solid.
- Submit early. Verify it went through.

**Done when:** submitted, verified, with buffer.

---

## Stretch goals (only after the must-ship is solid)

- A thin **second compound** added purely as data — proves the generic model (highest-value).
- **3D viewer** (`stmol`/`py3Dmol`).
- **Agentic search-to-approve** into the Reference tab.
- **MCP server** exposing the core to external agents.
- **Model-adapter** wired to a second model.

---

## Model division of labor

- **Opus (Claude)** — all biology/chemistry reasoning, strategy-library curation,
  analog-generation design, agent orchestration, **and the primary build via Claude Code.**
  Claude stays central (this is a Built with Claude submission; a required question asks how
  Claude and Claude Science were used).
- **Codex 5.6 / Grok (via Cursor)** — **review only, not building**: a fresh-eyes code-review
  pass after Claude Code builds; UI/plumbing/test suggestions on genuinely domain-free code.
- **The build must be Claude Code.** *(Confirm the multi-tool rule in the Discord; using other
  assistants for review is normal, but verify rather than assume.)*

---

## Daily discipline

- Start each session by re-reading the **scope** and **NOT THIS WEEK** list in PROJECT.md.
- Commit at the end of every day. Keep the repo clean. **Distinctive naming** on repos/files.
- New idea? Write it in `SOMEDAY.md` and keep building the plan. Scope creep is the enemy.
- **Sleep.** A rested Day 4 beats two fried ones. This project's edge is careful thinking,
  which is the first thing to go when exhausted.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| **Analog generation produces invalid structures** (#1) | Encoded transformations only; RDKit-validate everything; describe-and-highlight fallback; spike Day 1. |
| Compound-specific code leaks into the engine | The generic data model + the acceptance test; lock it Day 1. |
| Context blown by bloated papers | Extract-once to distilled records; agent reads records, not PDFs. |
| Overclaiming / hallucinated chemistry | Trust boundary + provenance tags + the two-way gate + honest-failure. |
| Scope creep | The NOT-THIS-WEEK list. Say no. Architect-for vs. build-now discipline. |
| Running out of time | Build finishes Day 4; Days 5–6 are polish/submit. |
| Claude Science unavailable/unclear | Built-in Reference tab stands alone; verify Claude Science from inside before relying. |

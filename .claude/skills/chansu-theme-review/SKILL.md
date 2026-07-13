---
name: chansu-theme-review
description: Review the Chansu Streamlit UI for violations of the chansu-design system. Invoke after building or changing any chansu/ui/ screen or component, before committing, to catch drift from the tokens, type registers, chemistry-notation rules, provenance discipline, and scientific voice. The quality gate that keeps new components on-brand as the app grows. Analogous to a per-page brand review; reads chansu-design as the source of truth.
---

# Chansu Theme Review

A quality gate. Run it against a changed screen, a new component, or the whole `chansu/ui/` package
and report every violation of the `chansu-design` system, most severe first, each with a concrete fix.
This does not restyle anything. It finds drift and hands back a report.

**Source of truth:** the `chansu-design` skill. Read it first. The tokens live in
`chansu/ui/theme.py`; the rendered reference is `docs/design/chansu-styleguide.html`.

## How to run

1. Read `chansu-design` (tokens, type registers, color law, notation rules, voice).
2. Determine scope: a single file the user named, the files changed in the working tree
   (`git diff --name-only -- chansu/ui/`), or all of `chansu/ui/*.py` if asked for a full sweep.
3. Read the in-scope files. Also read `theme.py` if any class or token is in question.
4. Walk the checklist below against every rendered string, class, color, and copy block.
5. Report using the output format. Do not fix unless the user asks; if they do, apply fixes and
   re-run the checklist on the result.

## Checklist (grouped by severity)

### Blocking (ship-stoppers)
- **Chemistry notation.** Any rendered formula without true sub/superscript
  (`C24H34O5` not `C₂₄H₃₄O₅`), ASCII Greek or descriptors (`beta`, `alpha`, `E-alkene`), missing
  italics on stereodescriptors/prefixes (*R*, *S*, *tert*-, *N*-), or notation not wrapped in
  `.cs-chem`. This is priority one; flag every instance.
- **Provenance discipline.** A scientific claim rendered without a provenance tag, or a prediction
  stated as fact. Every claim carries `[computed]` / `[literature · cited]` / `[reasoning · <model>]`
  / `[hypothesis]` / `[uncited]` (via `.cs-prov`). Never a cited tag the data cannot back.
- **Color law broken.** Brass (`--brass`) used to encode data, or a data color (`--high/med/low/
  pass/reason`) used for an interactive control. These two vocabularies never cross.

### Major
- **Type register wrong.** Serif outside inline chemical notation; machine data (SMILES, InChIKey,
  PMID, numeric property) not in mono; reading prose in mono.
- **Hardcoded values off-token.** A hex color, font, radius, or spacing literal that is not a token
  from `theme.py`. New shared values become tokens; one-offs are justified inline or removed.
- **Class contract abused.** A `.cs-*` class repurposed for a different meaning, or a new component
  built with inline styles that duplicates an existing class.
- **Declined state mis-styled.** A model-declined / honest-failure moment rendered in the flag or
  error register instead of the calm `.cs-declined` treatment.
- **Voice: em dash present**, or banned AI lexis (delve, seamless, unlock, leverage, robust,
  cutting-edge, elevate, harness, "not only … but also", rule-of-three), or an unhedged claim.

### Minor
- **Voice: over-explaining.** Copy longer than a chemist needs. State the fact and its source.
- **Spacing/radius off-scale.** Values not on the 4px rhythm; radius > 16px on a rectangle.
- **Motion not guarded.** A CSS animation not inside `@media (prefers-reduced-motion: no-preference)`.
- **Contrast.** Body text below 4.5:1, large heading below 3:1 on its background.

## Output format

```
CHANSU THEME REVIEW — <scope>
Source: chansu-design skill

BLOCKING
  <file>:<line>  <rule>  →  <what is wrong>  →  <fix>
MAJOR
  ...
MINOR
  ...

Summary: <n> blocking, <n> major, <n> minor. <one-line verdict>
```

If nothing is found, say so plainly and name what was checked. Do not invent violations to look
thorough. A clean screen is a valid result.

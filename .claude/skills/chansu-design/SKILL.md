---
name: chansu-design
description: The Chansu design system. Invoke at the start of ANY UI or copy work on the Chansu Streamlit app (chansu/ui/) so every screen, component, and string matches the brand instead of drifting to generic defaults. Provides the token system, the three type registers (with the serif-for-notation rule), the color law, chemistry-notation rules, component patterns, states, and the scientific voice rules. Chansu's equivalent of a brand theme factory; frontend-design is the general craft method underneath it.
---

# Chansu Design System

The locked visual and voice system for the Chansu Streamlit app. Read this before touching
`chansu/ui/`. The rendered reference lives at `docs/design/chansu-styleguide.html` (open it in a
browser). The implemented tokens live in `chansu/ui/theme.py` and `.streamlit/config.toml`.

**What Chansu is (for tone calibration):** a grounded medicinal-chemistry tool. A chemist loads a
natural compound, the engine grounds it in cited literature, grades which regions matter, matches
liabilities to precedent strategies, and generates RDKit-validated analogs. Every claim is
provenance-tagged. The visual system serves one goal: read as a real scientific instrument, not a
SaaS landing page and not a terminal.

---

## 1. The two laws

1. **Color is either brand or data. Never both.** Brass marks interaction and nothing else. A
   separate, desaturated palette carries the science (importance, gate state, provenance). If a
   color is decorative, remove it.
2. **Type register follows who reads it.** Sans for interface, mono for machine data, serif for
   human-readable chemistry. See §3. If you are unsure which register applies, you have a naming
   problem, not a styling problem: name the thing first.

---

## 2. Color tokens

Cool graphite ground, soft off-white text (never pure white), one brass accent.

```
/* graphite ground — depth without shadow */
--bg:         #0C0F12   page
--bg-alt:     #11151A   alt sections, sidebar, nav
--card:       #161B21   surfaces, panels, cards
--card-2:     #1D242C   elevated (dropdowns, modals)
--border:     #28313A   default border
--border-sub: #1A2026   subtle divider

/* text — soft off-white, never pure */
--ink:   #E7E9EB   primary (body, headings, structure ink)
--ink-2: #98A2AD   secondary (reasons, descriptions)
--ink-3: #5A6570   tertiary (labels, metadata, placeholder)

/* brand accent — INTERACTION ONLY */
--brass:        #C99A46   CTAs, links, focus ring, active tab, the mark
--brass-soft:   #D8B76C   hover only
--brass-dim:    rgba(201,154,70,0.12)   accent backgrounds
--brass-border: rgba(201,154,70,0.30)   accent borders

/* data palette — SCIENCE ONLY */
--high:  #D97070   importance high   AND gate flag      (meaning: critical)
--med:   #D4A24A   importance medium
--low:   #6E96B4   importance low     AND computed prov. (meaning: baseline)
--pass:  #68B18C   gate pass          AND literature-cited (meaning: verified)
--reason:#A796CB   reasoning provenance
```

**The reuse table is deliberate.** The palette stays small because colors double up only where the
meaning genuinely matches: red = critical (high importance / flag), green = verified (pass /
cited), slate = baseline (low / computed). Do not add a new color for a new state. Find the
existing meaning first.

**Rules**
- Never use brass for data. Never use a data color for an interactive control.
- Never use any accent for body text.
- The importance ramp (high red / medium amber / low slate) differs in luminance as well as hue, so
  it survives grayscale and colorblind reading. Preserve that when adjusting.
- **The importance ramp is the single vocabulary for importance everywhere, including the molecule
  viewer overlay.** The overlay uses the same `--high` / `--med` / `--low` colours as the pills, so
  the viewer legend and the grounding pills never disagree. The viewer does NOT get its own palette
  and there is no molecule-overlay colour exception. The red-vs-oxygen legibility concern is solved
  by the highlight *mechanism*, not by changing the colour: apply importance as a non-destructive
  highlight (a halo in 2D, a translucent shell/sphere around the region in 3D) so CPK element
  colouring (O red, N blue, C grey) stays visible underneath. Never recolour atoms to the importance
  colour.
- Contrast: body text on its background stays >= 4.5:1; large headings >= 3:1.

---

## 3. Type — three registers, one rule each

```
--font-sans:  'IBM Plex Sans'   interface prose, headings, labels
--font-mono:  'IBM Plex Mono'   ALL machine data + UI chrome
--font-serif: 'IBM Plex Serif'  human-readable chemistry notation ONLY
```

| Register | Renders | Never renders |
|---|---|---|
| **Sans** | headings, page titles, compound name as a title, interface copy, buttons, reasons | data identifiers |
| **Mono** | SMILES, InChIKey, PMIDs, DOIs, numeric properties, deltas, eyebrows, tags, table headers, metadata | reading prose |
| **Serif** | inline chemical notation: formulae (C<sub>24</sub>H<sub>34</sub>O<sub>5</sub>), stereodescriptors and locants (14β, (3*R*,5*R*), α-pyranone), IUPAC fragments, compound names *inside prose* | anything that is not chemistry-on-a-page |

**Serif is tightly scoped.** It exists to make chemical notation read like a journal. It must not
leak into UI narrative, headings, or general body text. Wrap serif notation in the `.cs-chem` class
(theme.py) or a single `chem()` render helper so it never spreads. When in doubt, it is Sans.

**Heading letter-spacing (negative, always):** display 54px `-0.035em`, xl 40px `-0.03em`,
lg 22px `-0.022em`, md `-0.015em`. Eyebrows and mono labels use positive `+0.12em`, uppercase.

**Eyebrow label** (the section-within-a-section device): mono, 11px, `+0.16em`, uppercase, brass.

---

## 4. Chemistry notation — the priority

This is the line between a real tool and a coded demo. Every rendered chemical string obeys these.
Do not ship notation that fails this table.

| Rule | Wrong | Right |
|---|---|---|
| Subscripts in formulae | `C24H34O5` | C<sub>24</sub>H<sub>34</sub>O<sub>5</sub> |
| Superscript charges | `Na+/K+-ATPase` | Na<sup>+</sup>/K<sup>+</sup>-ATPase |
| Greek stereo-locants | `14-beta-hydroxyl` | 14β-hydroxyl |
| Italic configuration | `(3R,5R)` | (3*R*,5*R*) |
| Italic locant prefixes | `tert-butyl`, `N-methyl` | *tert*-butyl, *N*-methyl |
| Ring / double-bond descriptors | `alpha-pyranone`, `E-alkene` | α-pyranone, (*E*)-alkene |
| Prime positions | `C3-prime` | C3′ |

**How to render in Streamlit:** markdown carries the Unicode directly (β, α, ′, ⁺, subscripts via
Unicode or `<sub>`/`<sup>` in an `unsafe_allow_html` block). Italic descriptors use `*R*` emphasis.
Keep this in a `chem()` helper in the UI/data layer, never in engine code (PROJECT.md §5).

Italic descriptor set to remember: *R S E Z cis trans tert- sec- o- m- p- N- O-*. Greek positions:
α β γ. Always use the real glyphs, not ASCII spellings.

---

## 5. Spacing, radius, motion

- **Spacing:** 8px rhythm. Values are multiples of 4. Vary spacing intentionally: tight groups,
  loose separates. `--s1..s8 = 4,8,16,24,32,48,64,96`.
- **Radius:** cards/panels 12–13px, buttons 9–10px, chips 4–5px, pills 999px. Never 20px+ on
  rectangles.
- **Borders:** hairline 1px. Depth comes from the graphite levels, not shadows. Shadow only for true
  elevation (modals), and light.
- **Motion:** subtle, precise, no bounce. Enter with `ease-out` or `cubic-bezier(0.16,1,0.3,1)` at
  220–350ms; exits at ~120ms. Everything animated is wrapped in
  `@media (prefers-reduced-motion: no-preference)`. Motion is background enhancement; the app must
  work perfectly with it off. See theme.py for the exact keyframes (content fade-in, hover lift,
  focus ring, active-tab indicator).

---

## 6. Components (map to the `cs-*` class contract in theme.py)

Do not rename these classes; app markup depends on them. Add new classes, do not repurpose.

- `.cs-eyebrow` — mono brass uppercase section label.
- `.cs-name` — the compound-name display heading (Sans, tight tracking).
- `.cs-sub` — muted supporting line under a name.
- `.cs-chip` — brass-tinted metadata chip (class annotation, etc.).
- `.cs-chem` — inline serif chemical notation (§3). Wrap all notation in this.
- `.cs-kv` (`.k`/`.v`) — mono key/value data rows. Keys uppercase mono `--ink-3`; values mono `--ink`.
- `.cs-stats` / `.cs-stat` (`.n`/`.l`, `.ok`/`.warn`) — computed-property mono stat strip.
- `.cs-card` (`.t`/`.d`) — panel with hairline border, hover lift.
- `.cs-cite` — mono brass citation line.
- `.cs-imp` (`.high`/`.medium`/`.low`) — importance pill, mono, from the data palette.
- `.cs-prov` (`.computed`/`.lit`/`.reason`/`.hyp`/`.uncited`) — provenance tag. Color-coded by
  source class per §2. This is the trust boundary rendered as a chip. Never state a prediction as
  fact; always attach the tag.
- `.cs-declined` — the honest-failure / model-declined state (§7).
- `.cs-rule` — hairline divider.

**Buttons:** primary = brass fill on dark ink text; outline = transparent, hairline border, brass on
hover; ghost = muted text, ink on hover. Hover lifts `translateY(-1px)`.

---

## 7. States, including honest failure

Chansu's honest-degradation moments are core to the product, not errors. Style them as calm facts.

- **Pass / verified** — `--pass`. Quiet, not celebratory.
- **Flag (high-importance edit)** — `--high` border + tint + label. A real gate act.
- **Declined (model safety layer)** — `.cs-declined`: muted neutral, marked, *calm*. Distinct from a
  red flag. The deterministic floor loses nothing when Claude declines, and the styling should say
  that, not alarm. Never render a decline in the flag/error register.
- **Focus** — brass `focus-visible` ring (Streamlit strips focus rings; theme.py restores it).

---

## 8. Voice — scientific register, no AI tells

The copy discipline is the trust boundary made verbal: terse, precise, hedged by provenance. Reads
like a biochemistry application or a journal, not marketing.

**Hard rules**
- **No em dashes.** Use a period, colon, parentheses, or restructure.
- **No AI phrasing.** Banned lexis: delve, seamless(ly), unlock, leverage, robust, cutting-edge,
  elevate, harness, testament, realm, landscape, "not only … but also", rule-of-three cadence,
  "it is worth noting", "in today's".
- **Hedge by provenance.** State predictions as predictions, cite what is cited, mark hypotheses.
  "Predicted ΔtPSA -9.2. Cited precedent: fluticasone." Never "this improves solubility."
- **Do not over-explain.** State the fact and its source. Detail where a chemist needs it (a
  mechanism, a locant, a citation), nowhere else. "C14 β-hydroxyl. High importance. Katz 2010."

**Provenance tag format (target):** `[computed]`, `[literature · cited]`, `[reasoning · <model>]`,
`[hypothesis]`, `[uncited]`. Middle dot, not em dash. NOTE: `chansu/report.py` still emits the
em-dash form `[literature — cited]`, asserted by five tests. Migrating it is a tracked follow-up
(update report.py and tests together). New styled UI components use the dot form now.

---

## 9. Logomark

The mark is the hexagon ring with a centered brass bond. It scales from favicon to footer. Asset:
`chansu/ui/assets/mark.svg` (and `mark.png` for the Streamlit `page_icon`). The full wordmark is
`logo-chansu-dark.png` (white on dark, for the sidebar header on the dark ground); `logo-chansu.png`
is the dark-ink-on-light version, not for this theme. Do not use the AC-monogram variant.

---

## 10. How to use this skill

1. Invoke this skill before any `chansu/ui/` work.
2. Build against the tokens and classes above. Add classes, never repurpose them.
3. Wrap chemical notation in `.cs-chem` / `chem()`. Tag every claim with `.cs-prov`.
4. Write copy in the §8 register.
5. Run the `chansu-theme-review` skill on the result before committing.

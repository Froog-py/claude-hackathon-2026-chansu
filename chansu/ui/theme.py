"""Chansu visual theme (spec: chansu-design skill).

A dark graphite lab identity taken from the logo: cool near-black ground, soft off-white ink, and a
single brass accent (the mark's centered bond). Injected once at app start. All chemistry/logic lives
elsewhere; this file only styles.

Three type registers (chansu-design skill): IBM Plex Sans for interface, IBM Plex Mono for every piece
of machine *data* (SMILES, InChIKey, properties, PMIDs), IBM Plex Serif reserved for inline chemical
notation (`.cs-chem`). Color is either brand (brass, interaction only) or data (importance / gate /
provenance); the two never mix. Motion is subtle and honours prefers-reduced-motion.

The `.cs-*` class names are a contract the app markup depends on; values change, names do not.
"""

from __future__ import annotations

import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Serif:ital,wght@0,400;0,500;1,400;1,500&display=swap');

:root{
  --bg:#0C0F12; --bg-alt:#11151A; --card:#161B21; --card-2:#1D242C;
  --border:#28313A; --border-sub:#1A2026;
  --ink:#E7E9EB; --ink-2:#98A2AD; --ink-3:#5A6570;
  --brass:#C99A46; --brass-soft:#D8B76C; --brass-dim:rgba(201,154,70,0.12); --brass-border:rgba(201,154,70,0.30);
  --high:#D97070; --med:#D4A24A; --low:#6E96B4; --pass:#68B18C; --reason:#A796CB;
  --font-sans:'IBM Plex Sans',system-ui,-apple-system,sans-serif;
  --font-mono:'IBM Plex Mono','SF Mono',monospace;
  --font-serif:'IBM Plex Serif',Georgia,serif;
}

/* --- surfaces + type ------------------------------------------------------ */
[data-testid="stAppViewContainer"], [data-testid="stHeader"] { background: var(--bg); }
[data-testid="stAppViewContainer"] {
  background-image: radial-gradient(circle at center, rgba(231,233,235,0.022) 1px, transparent 1.4px);
  background-size: 26px 45px; background-position: 0 0, 13px 22.5px;
}
[data-testid="stAppViewContainer"] * { font-family:var(--font-sans); }
/* restore Streamlit's Material icon font — the * rule above would clobber the ligatures */
[data-testid="stIconMaterial"] { font-family:'Material Symbols Rounded','Material Symbols Outlined' !important; }
.stMarkdown p, .stMarkdown li { color: var(--ink); line-height:1.62; letter-spacing:-0.005em; }
.stMarkdown a { color: var(--brass); text-decoration:none; border-bottom:1px solid transparent; transition:border-color 140ms ease; }
.stMarkdown a:hover { border-bottom-color: var(--brass-border); }
h1,h2,h3,h4 { font-family:var(--font-sans) !important; color:var(--ink) !important; font-weight:600 !important; }
h1 { letter-spacing:-0.035em; line-height:1.04; }
h2 { letter-spacing:-0.028em; }
h3 { letter-spacing:-0.02em; }
code, kbd, pre, [data-testid="stCode"] *, .stCode, [data-testid="stCodeBlock"] * { font-family:var(--font-mono) !important; }
[data-testid="stCodeBlock"], pre { background:var(--card) !important; border:1px solid var(--border) !important; border-radius:11px; }

/* app title (st.title) */
[data-testid="stAppViewContainer"] h1:first-of-type { font-size:2.4rem; letter-spacing:-0.038em; }

/* lift content: trim the main container top padding so the tab nav sits near the top */
[data-testid="stMain"] .block-container { padding-top: 2.4rem; }

/* Material icons (expander toggle, etc.) must keep their icon font, not the mono override above */
[data-testid="stExpander"] summary [data-testid="stIconMaterial"],
[data-testid="stExpander"] summary span[class*="material"],
[data-testid="stIconMaterial"] { font-family:'Material Symbols Rounded','Material Symbols Outlined','Material Icons' !important; }

/* --- sidebar -------------------------------------------------------------- */
[data-testid="stSidebar"] { background: var(--bg-alt); border-right:1px solid var(--border); }
[data-testid="stSidebar"] [data-testid="stImage"] img { border-radius:10px; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"], [data-testid="stSidebar"] .stCaption { color:var(--ink-3); }

/* --- tabs ----------------------------------------------------------------- */
.stTabs [data-baseweb="tab-list"] { gap:8px; border-bottom:1px solid var(--border); }
.stTabs [data-baseweb="tab"] { font-family:var(--font-mono); font-size:11.5px; letter-spacing:0.08em; text-transform:uppercase; color:var(--ink-3); padding:8px 6px; }
.stTabs [aria-selected="true"] { color:var(--ink) !important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { background:var(--brass) !important; transition:all 200ms ease; }

/* --- buttons -------------------------------------------------------------- */
.stButton>button, .stDownloadButton>button {
  border:1px solid var(--border); background:transparent; color:var(--ink);
  border-radius:9px; font-weight:500; font-family:var(--font-sans);
  transition:transform 160ms ease, border-color 140ms ease, color 140ms ease, background 140ms ease;
}
.stButton>button:hover, .stDownloadButton>button:hover { border-color:var(--brass-border); color:var(--brass-soft); transform:translateY(-1px); }
.stButton>button[kind="primary"] { background:var(--brass); border-color:var(--brass); color:#1c1405; font-weight:600; }
.stButton>button[kind="primary"]:hover { background:var(--brass-soft); border-color:var(--brass-soft); color:#1c1405; box-shadow:0 0 22px rgba(201,154,70,0.18); }

/* --- inputs / selects ----------------------------------------------------- */
[data-baseweb="select"]>div, .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"]>div {
  background:var(--card) !important; border-color:var(--border) !important; border-radius:9px !important; color:var(--ink) !important;
}
[data-baseweb="popover"], [data-baseweb="menu"] { background:var(--card-2) !important; }
.stRadio label, .stSelectbox label, .stTextInput label, .stTextArea label { color:var(--ink-2) !important; }

/* --- expanders + alerts + dividers --------------------------------------- */
[data-testid="stExpander"] { border:1px solid var(--border); border-radius:12px; background:var(--card); }
[data-testid="stExpander"] summary { font-family:var(--font-mono); font-size:12px; color:var(--ink-2); }
[data-testid="stExpander"] summary:hover { color:var(--ink); }
hr, [data-testid="stDivider"] { border-color:var(--border) !important; }

/* --- focus ring (Streamlit strips it) ------------------------------------- */
:focus-visible { outline:2px solid var(--brass-border) !important; outline-offset:2px; border-radius:6px; }

/* --- custom components (the cs-* class contract) -------------------------- */
.cs-eyebrow { font-family:var(--font-mono); font-size:11px; font-weight:500; letter-spacing:0.16em; text-transform:uppercase; color:var(--brass); margin:0 0 6px; }
.cs-name { font-family:var(--font-sans); font-size:2.4rem; font-weight:600; letter-spacing:-0.032em; line-height:1.04; color:var(--ink); margin:0; }
.cs-sub { color:var(--ink-2); font-size:0.95rem; margin:6px 0 0; }
.cs-chip { display:inline-block; font-family:var(--font-mono); font-size:11px; letter-spacing:0.04em; padding:3px 10px; border-radius:5px; background:var(--brass-dim); color:var(--brass-soft); border:1px solid var(--brass-border); }

/* inline chemical notation — serif, tightly scoped */
.cs-chem { font-family:var(--font-serif); }
.cs-chem i, .cs-chem em { font-style:italic; }

.cs-kv { display:flex; flex-wrap:wrap; gap:8px 26px; margin:14px 0 2px; }
.cs-kv .k { font-family:var(--font-mono); font-size:10.5px; letter-spacing:0.08em; text-transform:uppercase; color:var(--ink-3); }
.cs-kv .v { font-family:var(--font-mono); font-size:13px; color:var(--ink); word-break:break-all; }

.cs-stats { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:1px; background:var(--border-sub); border:1px solid var(--border-sub); border-radius:11px; overflow:hidden; }
@media (max-width:820px){ .cs-stats { grid-template-columns:repeat(3,minmax(0,1fr)); } }
.cs-stat { background:var(--card); padding:13px 15px; }
.cs-stat .n { font-family:var(--font-mono); font-size:1.14rem; font-weight:500; color:var(--ink); line-height:1.05; white-space:nowrap; letter-spacing:-0.01em; }
.cs-stat .l { font-family:var(--font-mono); font-size:9.5px; letter-spacing:0.08em; text-transform:uppercase; color:var(--ink-3); margin-top:7px; }
.cs-stat .n.ok { color:var(--pass); } .cs-stat .n.warn { color:var(--high); }

.cs-card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:15px 16px; margin:0 0 10px; transition:border-color 200ms ease, transform 340ms ease; }
.cs-card:hover { border-color:var(--brass-border); transform:translateY(-2px); }
.cs-card .t { font-weight:600; color:var(--ink); }
.cs-card .d { color:var(--ink-2); font-size:0.9rem; margin:2px 0 6px; }
.cs-cite { font-family:var(--font-mono); font-size:10.5px; letter-spacing:0.02em; color:var(--brass); }

.cs-imp { display:inline-block; font-family:var(--font-mono); font-size:10px; font-weight:500; letter-spacing:0.08em; text-transform:uppercase; padding:2px 9px; border-radius:4px; margin-right:8px; }
.cs-imp.high { background:rgba(217,112,112,0.13); color:var(--high); }
.cs-imp.medium { background:rgba(212,162,74,0.14); color:var(--med); }
.cs-imp.low { background:rgba(110,150,180,0.15); color:var(--low); }

/* gate flag — a gate act (§7): --high border + tint + label, distinct from the importance pill */
.cs-flag { display:inline-block; font-family:var(--font-mono); font-size:10px; font-weight:500; letter-spacing:0.08em; text-transform:uppercase; padding:2px 9px; border-radius:4px; margin-right:8px; color:var(--high); background:rgba(217,112,112,0.13); border:1px solid rgba(217,112,112,0.32); }

/* provenance tag — the trust boundary as a chip (color-coded by source class) */
.cs-prov { display:inline-flex; align-items:center; gap:6px; font-family:var(--font-mono); font-size:10.5px; letter-spacing:0.03em; padding:2px 9px; border-radius:5px; border:1px solid; white-space:nowrap; }
.cs-prov::before { content:''; width:6px; height:6px; border-radius:50%; background:currentColor; flex:none; }
.cs-prov.computed { color:var(--low); border-color:rgba(110,150,180,0.32); background:rgba(110,150,180,0.09); }
.cs-prov.lit { color:var(--pass); border-color:rgba(104,177,140,0.32); background:rgba(104,177,140,0.09); }
.cs-prov.reason { color:var(--reason); border-color:rgba(167,150,203,0.32); background:rgba(167,150,203,0.09); }
.cs-prov.hyp { color:var(--ink-2); border-color:rgba(152,162,173,0.32); background:transparent; border-style:dashed; }
.cs-prov.uncited { color:var(--ink-3); border-color:rgba(90,101,112,0.3); background:transparent; border-style:dashed; }

/* honest-failure / model-declined — calm, not an error */
.cs-declined { display:inline-flex; align-items:center; gap:7px; font-family:var(--font-mono); font-size:11px; letter-spacing:0.03em; color:var(--ink-2); background:var(--card-2); border:1px solid var(--border); border-radius:6px; padding:3px 10px; }

/* gate pass / verified — calm, quiet (not celebratory) (§7): --pass accent, no filled box */
.cs-pass { display:block; font-family:var(--font-sans); font-size:0.9rem; color:var(--ink-2); background:rgba(104,177,140,0.08); border:1px solid rgba(104,177,140,0.30); border-left:3px solid var(--pass); border-radius:8px; padding:10px 13px; }
.cs-pass b, .cs-pass strong { color:var(--pass); font-weight:600; }

/* gate flag — the §7 gate act: high-importance (--high) border + tint framing the .cs-flag label */
.cs-flagcard { background:rgba(217,112,112,0.06); border:1px solid rgba(217,112,112,0.32); border-radius:12px; padding:13px 15px; margin:0 0 10px; }

.cs-rule { height:1px; background:var(--border); border:0; margin:24px 0; }

/* --- motion (background enhancement; reduced-motion safe) ------------------ */
@media (prefers-reduced-motion: no-preference){
  @keyframes csFade { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:none; } }
  [data-testid="stMain"] .block-container { animation: csFade 420ms cubic-bezier(0.16,1,0.3,1) both; }
}
</style>
"""


def inject() -> None:
    """Inject the theme once, at the top of the app script."""
    st.markdown(_CSS, unsafe_allow_html=True)

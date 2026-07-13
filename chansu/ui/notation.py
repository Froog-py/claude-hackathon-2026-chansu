"""Chemistry-notation rendering for the UI (chansu-design skill sections 3 and 4).

Turns the ASCII chemistry in the curated data (for example ``Ca2+``, ``alpha-position``,
``C6H12O6``) into correct typographic notation: superscript charges, Greek locants, subscript
formulae, italic stereodescriptors. Compound-agnostic and presentation-only: it reads whatever
strings the data supplies and never mutates them (PROJECT.md sections 5 and 6).

Entry points:
  * ``sci(text)``   -> Unicode glyphs only (Greek, charges, primes), no markup. Safe in st.caption,
                       st.warning, and default markdown, where raw HTML would show literally.
  * ``chem(text, serif=True)`` -> escaped glyphs plus italic descriptors, optionally wrapped in the
                       serif ``.cs-chem`` span. For ``unsafe_allow_html`` blocks. serif=True for a
                       chemistry term (a name, a region label); serif=False for prose that embeds
                       chemistry (a reason) so the sentence stays in the interface sans.
  * ``formula(text)`` -> subscript every element count, wrapped serif. For a bare molecular formula.
"""

from __future__ import annotations

import html
import re

_GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "omega": "ω"}
_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def _greek(s: str) -> str:
    return re.sub(r"\b(alpha|beta|gamma|delta|omega)\b", lambda m: _GREEK[m.group(1)], s)


def _charges(s: str) -> str:
    # a '+' directly after an element letter is an ionic charge (e.g. a cation); a trailing '-'
    # is almost always a hyphen joining a following word, so it is left alone.
    return re.sub(r"(?<=[A-Za-z])\+(?![A-Za-z0-9])", "⁺", s)


def _primes(s: str) -> str:
    return re.sub(r"(?<=[A-Za-z0-9])'", "′", s)


def _glyphs(s: str) -> str:
    """Unicode-only transforms: safe in both markdown and HTML."""
    return _primes(_charges(_greek(s)))


def _italics(s: str) -> str:
    """Italic stereodescriptors and locant prefixes, as HTML (chansu-design section 4)."""
    s = re.sub(r"\(([RSEZ]|RS)\)", r"(<i>\1</i>)", s)
    return re.sub(r"\b(tert|sec|cis|trans)-", r"<i>\1</i>-", s)


def sci(text) -> str:
    """Glyphs only, no markup. For markdown / caption / warning contexts."""
    return _glyphs(str(text))


def chem(text, serif: bool = True) -> str:
    """Escaped glyphs plus italic descriptors, for ``unsafe_allow_html`` blocks."""
    inner = _italics(_glyphs(html.escape(str(text))))
    return f"<span class='cs-chem'>{inner}</span>" if serif else inner


def formula(text) -> str:
    """A bare molecular formula with subscripted element counts, serif-wrapped."""
    sub = re.sub(r"(\d+)", lambda m: m.group(1).translate(_SUB), html.escape(str(text)))
    return f"<span class='cs-chem'>{sub}</span>"

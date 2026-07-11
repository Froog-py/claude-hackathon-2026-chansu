"""Reasoning / agent layer (PROJECT.md §10, layer 2) — pluggable behind a model adapter.

Claude (Opus) drives this in production (wired Day 3). The interface in ``adapter`` is the
contract so other backends (a local model — stretch; Codex; etc.) can be swapped in without
touching the core. This week only the interface exists here; the Claude adapter lands Day 3.
"""

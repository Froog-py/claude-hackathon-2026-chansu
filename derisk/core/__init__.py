"""Core library — pure, framework-agnostic (PROJECT.md §10, layer 1).

Knows nothing about the UI, which model calls it, or any specific compound.
``models`` is dependency-free plain data; ``loaders``/``properties``/``generation``
add the RDKit-backed deterministic logic.
"""

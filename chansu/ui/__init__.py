"""Streamlit interface layer (PROJECT.md §10, layer 4; §11).

A thin skin over the framework-agnostic core: it composes the deterministic pipeline, the reasoning
adapter, and the render helpers into screens. All chemistry lives in the core and the render helpers —
this package only arranges and displays. Swapping the front-end replaces only this package.
"""

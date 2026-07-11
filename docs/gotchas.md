# Gotchas

Running list of non-obvious bugs and API quirks for this repo, grouped by area. **Read the
relevant section before touching that area.** Add an entry inline with the fix when a bug's
cause was surprising or cost real time; prune entries that go stale.

## Environment & setup

### RDKit needs Python ≤ 3.13 — there are no 3.14 wheels yet
The machine's default Python is 3.14, which has no RDKit wheel, so `pip install rdkit` fails.
Pin 3.12 with `uv venv --python 3.12 .venv`. `pyproject.toml` encodes `requires-python =
">=3.11,<3.14"` for the same reason.

### `timeout` is not on macOS by default
Scripts that wrap a command in `timeout` fail with "command not found"; it ships as `gtimeout`
via coreutils. Don't rely on `timeout` in Bash snippets here.

## RDKit / chemistry API

### `sascorer` lives in RDKit's Contrib tree, not the main namespace
Synthetic-accessibility scoring is not importable as `from rdkit.Chem import sascorer`. It is at
`RDConfig.RDContribDir/SA_Score/sascorer.py` — add that dir to `sys.path`, then `import
sascorer`. The pip `rdkit` wheel (2026.03) *does* include Contrib, so no vendoring is needed;
`properties.py` guards for its absence anyway.

### `AllChem.ReactionFromSmarts` **raises** on a malformed SMARTS — it does not return `None`
A missing `>>`, a single-`>` typo, an empty string, or unbalanced product parens raise a
`ValueError` (`ChemicalReactionParserException`). A `if rxn is None:` guard alone is dead code
for those cases. Wrap the parse in try/except so a data-authoring typo degrades to
describe-don't-break instead of crashing generation (see `chansu/core/generation.py`).
**Cost:** 2026-07-11 — caught by the Day-1 verification pass before it reached a real run.

### Attributing a reaction product to the parent atom it modified needs `react_atom_idx`
After `rxn.RunReactants((mol,))`, each product atom that came from the reactant carries the
props `old_mapno` (its SMARTS atom-map number) and `react_atom_idx` (its index in the parent
mol). Read both to know which position a product was made at — this is how position-targeted
generation and the two-way gate map products back to a site.

## Data & external sources

### PubChem renamed its SMILES properties
PUG REST no longer returns `CanonicalSMILES` / `IsomericSMILES`. Request `SMILES` (the
isomeric, stereo-bearing form) and `ConnectivitySMILES` (the flat, stereo-free form). For a
stereo-rich natural product like bufalin, the working structure must be `SMILES`, not the flat
one — the connectivity SMILES silently drops every stereocenter.

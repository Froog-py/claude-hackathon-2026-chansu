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

## Reasoning / models

### Ollama binds `127.0.0.1` by default — expose it before a remote client can reach it
An OpenAI-compatible call from another machine gets a fast "connection refused" (a ~3 ms RST, not
a timeout) because Ollama only listens on localhost. On the server set `OLLAMA_HOST=0.0.0.0:11434`
(Command Prompt: `set OLLAMA_HOST=0.0.0.0:11434`; PowerShell: `$env:OLLAMA_HOST="0.0.0.0:11434"` —
the syntaxes are NOT interchangeable and both fail silently if crossed), restart `ollama serve`
(the log must read `Listening on [::]:11434`, not `127.0.0.1`), and open the firewall for TCP
11434. Diagnose with `curl`, not `ping` — Windows blocks ICMP, so ping fails even when Ollama is
healthy. **Cost:** 2026-07-13 — several rounds wiring the cross-machine local model (Mac → Windows).

### OpenAI-compatible models return `finish_reason: "stop"`, which the reasoning layer rejects unless mapped
`design_reasoning._usable_text` accepts a completion only when `stop_reason in ("end_turn",
"stop_sequence")`. OpenAI and Ollama return `"stop"`, so `OpenAICompatibleReasoningModel` must map
`stop→end_turn` (also `length→max_tokens`, `content_filter→refusal`) via its `_FINISH_MAP`; without
that, a model's good answers are silently discarded as "unusable." Keep the map in sync if you
touch either file.

### `max_tokens` is provider-specific — Claude's 16k is a thinking budget, not a general default
The reasoning layer requests `max_tokens=16000` because Opus's hidden thinking tokens count against
it. OpenAI and local models emit only visible tokens, so `OpenAICompatibleReasoningModel` caps to
`default_max_tokens=2048`. Sending a 16k `num_predict` to a small local model is wasteful and can
strain its context window.

### OpenAI `429 insufficient_quota` is a valid key with no account credit, not a bad key
A missing/bad key returns 401; a `429 insufficient_quota` authenticated fine but the account has no
billing balance. The adapter surfaces it as a calm decline (no crash); the fix is account-side (add
credit), not code.

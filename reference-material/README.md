# Reference material

The literature workspace the pipeline reads from (PROJECT.md §9, kickoff "Reference-material
folder"). Claude Code owns and maintains this folder.

## Layout

- **`research-log/`** — the chemist's own research log: the flagship reference set for bufalin
  (targets, binding-site claims, importance/pharmacophore claims, liabilities, mechanisms,
  citations). Loaded as the Day-3 flagship literature. *To be added.*
- **`papers/`** — saved papers as links, citations, or PDFs. Documents need not be
  downloadable — a link + citation is enough.
- **`distilled-records/`** — the compact structured records the extraction pipeline produces
  (**extract-once, reuse-many**). The reasoning agent reads these, **not** raw PDFs.

## Workflow (Day 3+)

1. A paper enters via `papers/` (or the future agentic search-to-approve flow).
2. A lightweight extraction pass distills it to a structured record in `distilled-records/`
   — binding-site claims, importance claims, liabilities, mechanisms, and the citation.
3. The reasoning agent reads the distilled records. Each paper is processed once.

**Never fabricate a citation.** A record without a real source does not get written.

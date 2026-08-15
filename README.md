# antcat-pipelines

The pipeline code for Brian Fisher's AntCat data workstreams. One repo, one
truth: "current" = `main`. Session-start line for the AntCat and TaxonWorks
Claude projects: *"AntCat pipelines: canonical code and runbooks at
github.com/bpescador/antcat-pipelines. Fetch the relevant runbook before
acting."*

## The two pipelines

**AntCat → TaxonWorks sync** (repo root). Exports AntCat names, references,
and origin-citation links for import into TaxonWorks. Runbook: `WORKFLOW.md`
(six stages, AntCat export through production verify). Deep TW-side detail:
`antcat_dwca_checklist_import.md`.

**Bolton NGC ⇄ AntCat annual diff** (`bolton/`). Parses Barry Bolton's New
General Catalogue and diffs it against AntCat: references, species-group and
genus-group names, status citations, type material. Runbook:
`bolton/BOLTON_SYNC_RUNBOOK.md` (v2 — supersedes v1; lessons from the July
2026 run in `bolton/CHANGELOG_ENTRY.md`).

## Shared code

`protonym.py` (repo root) is the name-identity module — protonym parsing,
HTML stripping, accent folding, author keys — used by the TW exporters and
built originally for the Bolton diff. Single copy, lives here. (The bolton/
scripts currently carry embedded copies of some helpers from before the
extraction; consolidating them onto the shared module is a refactor for the
next annual cycle, not before.)

## What does NOT live here

- **Data** — dumps, CSV/TSV exports, .bib files. Regenerated each cycle;
  `.gitignore` enforces it. Data lives in `~/antcat/` working folders with
  dated, immutable zip snapshots in `~/antcat/snapshots/`.
- **Droplet operations docs** (infrastructure reference, ops runbook). This
  repo is public; those documents carry the origin server IP and internals
  that Cloudflare exists to hide. They stay in the AntCat Claude project's
  knowledge, deliberately.
- **Secrets** — never, anywhere: not in git, not in chat, not in project
  knowledge. Tokens live in env vars.

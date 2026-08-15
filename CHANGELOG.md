# antcat-tw-sync — changelog

## 2026-08-15 -- TW payload reconciled; workflow unified
- WORKFLOW.md: merged the TaxonWorks project's ANTCAT_TW_WORKFLOW.md into the
  single process doc (standing rules, TW-side Stages 4-6, unified gotchas).
- Added antcat_dwca_checklist_import.md (751-line TW import runbook).
- Rejected from the payload as OLDER than main: export_references.rb (stale
  _v2 header), export_antcat_bibtex.py (missing square-bracket balancing).
  push_to_repo.sh discarded (blind overwrite; normal git flow instead).
- Verified identical to main: export_antcat_names.py, protonym.py,
  build_origin_citation_links.py, build_tw_exports.sh.

## 2026-08-14 — repo consolidated (AntCat project session)
- All pipeline code gathered into this repo from three scattered sources
  (references3_final folder, taxonworks_sync bundle, project knowledge).
- `export_antcat_names.py`: the PAGE_RE-patched version (2026-08-11 fix:
  DOI-safe pages, PDF form preserved). Verified identical to the AntCat
  project-knowledge copy.
- `export_references.rb`: header comment fixed (claimed `_v2` filename and
  output; actual is `export_references.rb` → `antcat_references.csv`).
  Code unchanged.
- Known input-consistency state: Aug-14 dump cites 4,200 distinct references;
  the Jul-11 .bib lacks exactly 4 of them (144722, 144727, 144729, 144732 —
  new 2026 refs). Closes automatically on next same-moment CSV+dump regen.
- Still missing from repo: protonym.py, build_origin_citation_links.py
  (see README).

## 2026-07-11/12 — pipeline built (TaxonWorks project)
- export_references.rb (nested-container resolution), export_antcat_bibtex.py
  (crossref nesting, brace-safe), build_tw_exports.sh (one-command build with
  strict validation), TW_EXPORT_RUN_CHECKLIST.md.

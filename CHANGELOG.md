# antcat-tw-sync — changelog

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

# antcat-pipelines — changelog

## 2026-08-15d -- requirements.txt, data_currency.sh (from the genomics review)
- requirements.txt: bibtexparser<2 (Stage-2 gate, v1 API) and python-docx
  (parse_bolton). smoke.sh now warns if bibtexparser v1 isn't importable.
- data_currency.sh: lists every data input with age + md5 and applies the
  same-moment rule to the newest dump/CSV pair (PAIR OK / PAIR FAIL). Run
  before attaching or pairing inputs -- the "which file is current" habit,
  made one command. Self-tested both cases; portable Mac/Linux.
- CLAUDE.md session pattern updated to use both.
- Decision recorded: repo stays PUBLIC. Chat sessions clone by HTTPS with no
  ssh, so deploy keys can't serve them; private would revert self-fetch to
  Brian attaching archives. Audit shows nothing sensitive in the repo.

## 2026-08-15c -- pre-commit smoke test and provenance rule
- smoke.sh added (syntax-checks every .py/.sh/.rb; tripwires for the PAGE_RE
  fix, the canonical diff_history branch, and BibTeX bracket balancing).
  CLAUDE.md now requires SMOKE PASS before any commit, and commit-hash + md5
  logging for any script copied to a server. Adapted from the genomics
  dashboard project's BUILD_TAG lesson: git is the version marker here;
  detachment is where identity gets logged.

## 2026-08-15b -- bolton/ completed and repaired from the round-9 master bundle
- diff_history.py REPLACED: the committed 307-line copy was the wrong branch
  (pre-fuzzy, pre-citation-fix; would produce ~1,418 phantom rows). Canonical =
  the 761-line round-7/round-9 version (byte-identical across three archive
  copies), which supersedes BOTH the Round-3 same_epi fuzzy matchers and the
  citation-key patch via gstem-indexed act matching. diff_history_citation-key
  .patch removed as a superseded artifact of the wrong-branch merge attempt.
- ADDED from the master bundle (all syntax-checked): parse_antcat.py (required
  import of diff_history/diff_catalogue), diff_status_refs.py,
  resolve_status_refs.py, export_references_ws1.rb (the WS1 reference-table
  dump; distinct from the validated root TW exporter), and
  ANTCAT_COMPARISON_MASTER.md (the three-workstream architecture doc).
- UPDATED from the master bundle (newer than the project-knowledge copies):
  parse_bolton.py (252->272 ln), diff_catalogue.py (235->259 ln).
- RECOVERED from chat history verbatim: institutions_export.rb (7 lines,
  confirmed against its logged production run: 784 rows).
- KEPT repo versions over master (repo newer): protonym.py (docstring-only
  churn; this copy reproduced the validated 23,100-name build),
  export_antcat_names.py (master predates the PAGE_RE fix), root
  export_references.rb (master's copy = same minus the header fix).
- Invocation note: bolton scripts import protonym (repo root) and parse_antcat
  (bolton/) -- run from repo root with PYTHONPATH=.:bolton
- STILL CHAT-ONLY, pinned for a dedicated retrieval session:
  (1) the July production writer suite (dry-run/canary/batch/manual) --
      chat "Batch writing 563 taxonomic status citations to AntCat",
      claude.ai/chat/d8b284fa-f57a-4a7a-99fb-139512cf5eed;
  (2) history_order_export.rb (its findings are fully preserved in
      BOLTON_SYNC_RUNBOOK.md section 2A) -- chat "Mapping NGC type material
      to AntCat fields", claude.ai/chat/a0e22ff4-3ba1-442b-9460-9fd0ea0de8f9.

## 2026-08-15 -- repo broadened: antcat-tw-sync -> antcat-pipelines
- Renamed; now the single home for both AntCat pipelines. TW-sync files stay
  at repo root (paths, curl lines, and checklists unchanged); the Bolton NGC
  annual-diff toolkit added under bolton/.
- bolton/ contents (from AntCat project knowledge + round_9 bundle):
  parse_bolton.py, diff_history.py, diff_catalogue.py,
  diff_history_citation-key.patch (provenance; may be pre-applied),
  citation_match.py, type_recon.rb, export_protonyms.rb, RUNBOOK.md,
  BOLTON_SYNC_RUNBOOK.md (= v2 FINAL, supersedes v1), CHANGELOG_ENTRY.md.
- README rewritten as the index of both pipelines; WORKFLOW.md URLs updated
  for the rename.
- Droplet ops docs deliberately excluded: public repo, and they carry the
  origin IP that Cloudflare exists to hide. They remain in AntCat project
  knowledge.

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

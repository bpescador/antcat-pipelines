# antcat-pipelines — changelog

## 2026-10-23 -- bolton/diff_depositories.py (depository resolver, recovered)
- The July 2026 depository resolver and diff existed only as inline steps in the
  chat "Mapping NGC type material to AntCat fields" (2026-07-23, turns 13, 19,
  21), passing pickles between steps. Rebuilt as one script; `--july` runs the
  July logic exactly.
- V2 (default): Bradley's crosswalk CSV as a third alias source ("same" and
  "same-for-comparison" rows only); hyphenated codes (NMNH-S) and known spaced
  codes ("NMNH NASU") read whole; sorted iteration; residual sheet gains
  antcat_url and the AntCat depository segments; metrics.json per run.
- Parity (same day, --july on fresh exports; the July inputs no longer exist):
  matched 22,298, split 20,048/298/1,941/11 and 11 fill candidates all equal
  July; 21 errata codes and 47 records equal July's list except MHNW, the code
  July noted as reading two ways (July kept MNHW from set order, sorted order
  keeps MHNG; the reviewer says NHMW). Residual 636 vs July 740: AntCat
  [Also] edits since July.
- --errata added (reviewer-confirmed typos override the automatic guess).
- bolton/depository_review_sheet.py: residual run -> reviewer workbook (Read me,
  Conflicts B, NGC has more A, Fill), decision list, optional hints CSV.
- AntCat label fix (V2): July read only "Primary/Secondary type depository/-ies:".
  AntCat also writes "Type-depository:" (1,105 records, left out of the July
  comparison altogether), "Paratype-depositories:" (254) and "... depositories
  and specimens:" (116, whose codes July missed, so they showed as "NGC has
  more"). 69 of the 111 A rows of the first V2 run were this bug.
- V2 run after the fix (2026-10-23, crosswalk 188 pairs, 21 confirmed errata):
  19,065 comparable, 97.0%, residual 567 = A 41 / B 83 / C 443. Numbers in
  BOLTON_SYNC_RUNBOOK.md section 5.

## 2026-09-28 -- build_name_dictionary.py (old name -> valid name)
- New script, repo root: builds Steve Shattuck's dictionary of old species-group
  names and their current valid names from a worldants dump. First run on the
  2026-09-28 dump: 14,957 rows (9,334 obsolete combinations, 5,153 synonyms,
  470 misspellings); 2,627 needed more than one hop; 77 old names map to more
  than one valid name (old homonymous combinations); 265 chains end at a
  non-valid name and are flagged rather than dropped. Junior homonyms are not
  included: the dump carries no replacement name for them (export_antcat_names.py
  resolves those from the history prose, if ever needed here).
- Two dump facts worth keeping: `current valid name` is ONE hop (a misspelling
  can point at a synonym), and it is prefixed with the subfamily.
- .gitignore: antcat__name_dictionary_*.csv (output is data).

## 2026-08-23 -- reciprocal adoption from the genomics repos' Guide v2
- CLAUDE.md rules 8-9 added: anchor-asserted scripted edits (all files, not
  just docs) and WHERE-headed, &&-chained command blocks. Both were already
  this project's practice; now they are written down, per our own rule that
  sessions only know what is written down.

## 2026-08-16 -- smoke boundary stated (from the dashboard project's review)
- CLAUDE.md rule 6: smoke proves the code, not the pipeline. Data-side gates
  (Stage 2/3 gates, the diff_history counts oracle) run only where data
  lives; SMOKE PASS on a fresh clone is never evidence a run is correct.
  Applies to every repo on this model; this one is the reference.

## 2026-08-15d -- requirements.txt, data_currency.sh (from the genomics review)
- requirements.txt: bibtexparser<2 (Stage-2 gate, v1 API) and python-docx
  (parse_bolton). smoke.sh now warns if bibtexparser v1 isn't importable.
- data_currency.sh: lists every data input with age + md5 and applies the
  same-moment rule to the newest dump/CSV pair (PAIR OK / PAIR FAIL). Run
  before attaching or pairing inputs -- the "which file is current" habit,
  made one command. Self-tested both cases; portable Mac/Linux.
- CLAUDE.md session pattern updated to use both.
- data_currency.sh v2 (after first live run): searches subfolders for the
  newest dump/CSV, and reports byte-identical copies under different
  names/ages ("DUPLICATE CONTENT") so superseded inputs get snapshotted.
  First run's finding: the Aug-14 and Aug-15 reference CSVs are md5-identical
  (no reference-table change) -- verdict still keyed to export time, because
  the same-moment rule is about provenance, not bytes.
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

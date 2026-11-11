# antcat-pipelines — changelog

## 2026-11-11 -- antweb_types/typestatus_corrections.py
- New, read only: turns the refreshed type-status sheet plus a returned week workbook into
  correction lists by the AntWeb record's source (TaxonWorks, upload group 76 = MZSP, other),
  since a fix only sticks at the source. Listed: rows the reviewer answered "AntCat", and two
  rules his week 3 samples confirmed (syntypes in AntCat, 10 of 10; paralectotype where AntCat
  codes the lectotype, 7 of 10 with the 3 unsure excluded). Target is always the AntCat protonym,
  with the TaxonWorks name key from antcat_names.tsv. Codes inside AntCat "X to Y" ranges with the
  same AntWeb status are added. Week 3 result: TaxonWorks 131, group 76 129, other 3; 118 not listed.

## 2026-11-11 -- TaxonWorks sync fixes: original-description page; references export under Ruby 4.0
- export_antcat_names.py: `original_page()` reads only the protonym's own citation (first year in
  the history text) and returns blank unless the token after its colon is arabic. It used to take
  the first year-colon-number anywhere in the first 200 characters, so a roman, plate or missing
  page fell through to a later citation: 21 names on the 11 Nov dump, all now blank (e.g. Myrmica
  reticulata 514828 had "5" from a 2026 lectotype designation). No other column or row changes;
  the 1,402 protonym citations with a DOI token are unchanged. smoke.sh checks nine cases.
- export_antcat_names.py, same day: the citation's DOI may be written as a link ("https://doi.org/...",
  "http://dx.doi.org/...", "doi: ..."); the parser now steps over these as over a bare DOI. 76 names
  go from blank to their real page (5 to 668), each checked as the number after the link's colon; no
  other row or column changes. Myrmoteras yamanei stays blank (a space inside its DOI in AntCat).
  smoke.sh: four more cases.
- export_references.rb: `require 'csv'` falls back to Ruby's bundled csv gem (newest version under
  Gem.default_dir) when bundler hides it, as on AntCat with Ruby 4.0; aborts with a message if no
  copy exists. Writes to /app/tmp first and copies over the CSV at the end (a copy, not a rename, so no
  write permission on /app is needed), so a failed run cannot leave a partial CSV under the real name.
- WORKFLOW.md / TW_EXPORT_RUN_CHECKLIST.md: check the CSV's date before copying; 2026-11-11 history.

## 2026-11-08 -- antweb_types: run on the 8 Nov exports; two linker faults fixed; reviewer week tools
- Inputs (same day): AntCat protonyms, institutions and flags (runners at 1de7a9f, run as antcat);
  AntWeb dump antweb-all-specimens-2026-11-08.tsv.gz (911,246 rows, md5 39f2cdbf), after the
  AntWeb project made the dump script read its credentials instead of holding a password.
- reconcile_types.py: 36,594 AntWeb type specimens (June 36,108); 10,453 already on AntCat;
  25,983 not (auto 22,297); 158 misplacements, 205 rank disagreements, 431 AntWeb name fixes.
- build_inserts.py, two faults found (commits eca9815, fdae8b9):
  - NGC-style labels ("Type-depository:") were not read as a depository: 407 of 425
    add_depository rows would have added a second depository line. June's 438 had the same fault.
    Now 18 add_depository rows.
  - present_check: 139 codes on 81 protonyms are already in AntCat, in type notes or written
    another way ("USNM# 609605"). reconcile_types.py's regex misses them.
  - Result: 8,611 protonyms (specimen line 7,334, append 1,133, full block 126, depository 18),
    104 held by convention, 1,585 material flags.
- New, read only:
  - bolton/ngc_labels.py: drafts AntCat labels for the 1,208 protonyms still using NGC labels
    (Type-X -> Primary type X; Paratype-X -> Secondary type X); asserts only labels change.
  - antweb_types/refresh_typestatus_sheet.py: brings a reviewer's type-status sheet up to date
    with a new run, carrying his answers; marks resolved, open and new rows; groups misplacements;
    shows patterns from AntCat's own data (replacement name, lectotype designated, syntypes in
    AntCat) as evidence. Bradley's 430 rows: 73 resolved (62 by his TaxonWorks fixes reaching
    AntWeb), 357 open, 6 new.
  - antweb_types/typestatus_week.py: day CSVs and week.json for bolton/review_week.py.
- bolton/review_week.py: optional "reference" tabs (shown, not timed) and "link_note".

## 2026-11-03 -- Rails runners run as user antcat
- Checked on antcat-staging: `docker exec antcat-app id` is root, while `/app/tmp` and
  `/app/log` belong to antcat (the app runs as antcat since AntCat #1578, 18 Oct). A runner
  started as root can leave root-owned files the app cannot write.
- The runner command in WORKFLOW.md, TW_EXPORT_RUN_CHECKLIST.md, BOLTON_SYNC_RUNBOOK.md
  (with the reason), ANTCAT_COMPARISON_MASTER.md and antweb_types/README.md now has `-u antcat`.
  Header comments of older runners are left as they are, so their md5s stay the same.
- export_protonym_flags.rb, tested on staging as antcat at 9d35f7e: 24,376 of 24,376 written,
  0 errors; replacement names 373 (+491 by history text), nomina nuda 314, all-unavailable
  1,396, quadrinomials 1,215. ActiveRecord logging is now off in the runner (staging printed
  300 KB of SQL at DEBUG).

## 2026-11-03 -- antweb_types: AntCat's type-information conventions, depository check, split fields
- build_inserts.py takes two optional inputs; without them the output equals the June output
  (selftest compares add_text):
  - `--flags=protonym_flags.jsonl` (new read-only runner `export_protonym_flags.rb`): rows for
    protonyms AntCat gives no type information under (Bradley, 2026-10-30) go to
    primary_adds_held.csv with a hold_reason: nomen nudum, replacement name (history item or
    homonym link, checked against the AntCat schema at 90407c3d9), unavailable name, quadrinomial
    to check.
  - `--institutions=institutions.jsonl`: depository_check flags AntWeb ownedby values that are
    not AntCat codes, and names the AntCat code behind an [Also]/[Formerly] alias.
- New columns primary_add and secondary_add: the text for each AntCat field. A full block's
  paratype text no longer has to be cut out of add_text by hand.
- selftest.py: a second run with both options (holds, alias, non-code, split columns). Breaking
  the replacement-name hold or the alias makes it fail.
- The runner has been syntax-checked only. Run it on antcat-staging first.

## 2026-11-03 -- depository scripts read mixed-case codes (INBio)
- The reviewer found INBio missed in the 2 Nov week (Temnothorax nebliselva): both scripts
  read codes as upper-case runs only. AntCat has four mixed-case codes: INBio, CeNak,
  PMSPbU, Raffles.
- diff_depositories.py: literal_codes() now matches mixed-case codes literally, as it
  already did for spaced ones ("NMNH NASU"). 30 Oct inputs: residual 588 -> 586 (A 35 -> 33;
  201811 and 201899, NGC INBC = AntCat INBio through its [Also] note); nothing else changed.
  --july output byte-identical before and after.
- split_depository_specimens.py: optional third argument institutions.jsonl; with it,
  mixed-case codes are read. 30 Oct export: 1 of 117 drafts changes (201899 gains INBio);
  without the argument the output is byte-identical to before.
- smoke.sh: tripwires for both.

## 2026-11-03 -- antweb_types/ (AntWeb type-specimen linker, recovered)
- The June 2026 AntWeb ⇄ AntCat type linker existed only in the sandbox of the chat
  "Automating type specimen linking between Antcat and Antweb" (7b114e80, 8 Jun 2026).
  Rebuilt by replaying every create_file, str_replace and patch script in the order
  it ran, each anchor asserted. No logic changes.
- reconcile_types.py (matcher), build_inserts.py (primary_adds.csv), the June README
  as last edited, and june2026/ one-offs (validation checklist, coverage counts) kept
  verbatim with provenance headers.
- New: antweb_types/selftest.py checks the June decisions on a made-up fixture
  (spaced codes, rank swaps, connecting words and gender endings not fixes, spelling
  vs current combination, misplacement, bare-holotype routing, no AntWeb locality,
  material flag). Undoing the spaced-code fix or adding a locality makes it fail.
  smoke.sh runs it and has two new tripwires.
- antweb_types/README.md: provenance per file, run steps with current paths, June
  final numbers (fix list 426, not the README's 772), and what must happen before
  any write (write runner, split primary/secondary, Bradley's no-type-info cases).

## 2026-10-30 -- diff_depositories.py: genus-aware matching; record-specific errata
- Found from the reviewer's returned week: July matched NGC to AntCat on (epithet,
  first author, year) and kept the FIRST record of each side, so two species sharing
  all three were crossed (Cerapachys turneri Forel 1902h got Dolichoderus turneri's
  NGC depositories). 848 AntCat and 794 NGC keys are shared. 17 of the 143 record rows
  in the 26 Oct week came from such crossings (7 of 13 on Day 5; 6 of the 11 fills).
- V2 splits a shared key by original genus, then by full name (genus and all
  epithets, subgenus and rank words dropped); what is still not one-to-one is left
  unmatched and listed in unmatched_shared_keys.csv (99 on the 30 Oct data: 55
  infrasubspecific names with no NGC entry, about 30 quadrinomials whose trinomial is
  matched, a few identical homonyms on both sides).
- 30 Oct run (exports md5 412e9486 / 9ef79a35, crosswalk and errata of 30 Oct):
  23,512 matched, 20,198 comparable, 97.1%, residual 588 = A 35 / B 70 / C 483.
  Of the 105 A+B rows, 102 were decided by the reviewer in the 26 Oct week; 3 are new.
- --errata rows may carry protonym_id: OMNH -> ONHM applies to three Arabian records
  only, since OMNH is a real code (Osaka) everywhere else.
- --july unchanged (byte-identical residual).
- bolton/split_depository_specimens.py: drafts the split of AntCat's combined
  "... depositories and specimens:" fields (117 on 30 Oct) into a depositories list and a
  specimens field, markup kept; flags commas used where semicolons separate codes.
  Checked: every code before a colon in each field is in its draft list.
- review_week.py: each day tab gets a yellow "actual time" cell, so estimates can be
  set from the reviewer's times (week 1 ran over, Day 4 most).
- Fill-candidate lesson from the reviewer: AntCat gives no type information under
  replacement names, nomina nuda, or quadrinomials whose name was later used at
  another rank. A fill list must exclude them before it reaches anyone.

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
- Reviewer-load tools: depository_triage.py (bucket, suggested decision and
  evidence per A/B row: same-collection pair, AntCat notes already mention the
  code, Bolton's author-to-depository index, quoted original description, or
  nothing); draft_type_text.py (NGC type block -> draft AntCat primary /
  secondary / notes text, for fill records); review_week.py (one workbook, one
  tab per day, time estimate per tab from per-row minutes). First use: a
  five-day package for the reviewer, about 9.5 hours in all.
- Lesson: summarised web fetches misreport exact data (one gave MZSP where
  AntCat says DZUP). Evidence quotes come from AntCat's own export or from
  the paper text, never from a summary.

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

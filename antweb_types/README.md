# antweb_types — AntWeb type specimens onto AntCat protonyms

This folder finds AntWeb type specimens whose codes are not yet in an AntCat protonym's type
fields and routes each to its protonym. It writes the exact text to add, and lists where the two
databases disagree. It is read-side only: nothing here writes to AntCat.

The code was built in June 2026 in the claude.ai chat "Automating type specimen linking between
Antcat and Antweb" (chat 7b114e80, 8 Jun 2026) and never left that chat's sandbox. It was
recovered on 2026-11-03.

## Files

| file | what | from |
|---|---|---|
| `reconcile_types.py` | matcher: tiers, AntWeb fix list, rank and misplacement lists | chat turn 19, edited in turns 21, 25, 39 |
| `build_inserts.py` | `primary_adds.csv`: one row per protonym, with the text to add | turn 35 |
| `AntCat-AntWeb_Type_Reconciliation_README.md` | the June method, rules and numbers, as last edited | turn 19, edited in turns 19, 21, 27, 29, 35 |
| `selftest.py` | new: checks the June decisions on a small made-up fixture | 2026-11-03 |
| `export_protonym_flags.rb` | new: read-only runner; per protonym, the facts the conventions need (name type, nomen nudum, replacement name, taxon statuses) | 2026-11-03 |
| `refresh_typestatus_sheet.py` | new: brings the reviewer's type-status sheet up to date with a new run, keeping his answers | 2026-11-08 |
| `typestatus_week.py` | new: builds his week (day CSVs + week.json for `bolton/review_week.py`) | 2026-11-08 |
| `typestatus_corrections.py` | new: reviewed and rule-confirmed corrections, split by AntWeb source (TaxonWorks, upload group 76, other) | 2026-11-11 |
| `june2026/` | one-off steps (validation checklist, coverage counts), verbatim, June paths | turns 37, 40, 48, 50 |

**How the files were rebuilt.** Every `create_file`, `str_replace` and patch script in the chat
was replayed in the order it ran, and each one's anchor text was found. There are no logic
changes. The only additions are the header comments on the `june2026/` files and `selftest.py`.
The first README refresh in turn 35 failed in June (NameError before writing) and fails the same
way on replay.

`export_protonyms.rb` (the AntCat side) is `bolton/export_protonyms.rb`, the same file the June
chat wrote in turn 9.

## Run

The data stays out of git. Put the inputs and outputs in `~/antcat/snapshots/types-YYYYMMDD/`.
Take the two exports on the same day.

1. **AntCat protonyms.** On the droplet, copy `bolton/export_protonyms.rb` into
   `/var/www/antcat-2/tmp/` from a pinned commit. Record the commit and md5, as in CLAUDE.md
   rule 7. Run it with the runbook command:
   `docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/export_protonyms.rb`.
   Use `-u antcat`: the container's default user is root, and the app runs as antcat.
   This is read-only. Copy `tmp/protonyms_species_typeinfo.jsonl` to the Mac, then clear `tmp/`.
   - Ignore the "Server export" block in the June README: it copies into the code folder, which
     is no longer done.
2. **AntWeb specimens.** On the AntWeb server, run `bash /root/antweb-specimen-dump.sh`. It writes
   `/root/antweb-exports/antweb-all-specimens-YYYY-MM-DD.tsv.gz`. In June that was 907,677 rows
   and 37 MB, with about 36,000 type specimens.
   - The script belongs to AntWeb and is not in this public repo, because it passes a database
     password.
   - It is tab-separated. Some rows are not UTF-8; the matcher reads them with
     `errors='replace'`.
3. `python3 antweb_types/reconcile_types.py protonyms_species_typeinfo.jsonl aw.tsv OUT/`
4. `python3 antweb_types/build_inserts.py protonyms_species_typeinfo.jsonl aw.tsv OUT/type_link_queue.csv OUT/ --flags=protonym_flags.jsonl --institutions=institutions.jsonl`
   - `protonym_flags.jsonl` comes from `antweb_types/export_protonym_flags.rb`, run like step 1. It is read-only.
   - `institutions.jsonl` comes from `bolton/institutions_export.rb`.
   - Without the two options the output is the June output.
5. Before trusting a run after any code change, `python3 antweb_types/selftest.py` must print
   SELFTEST PASS. `smoke.sh` runs it too.
6. Reviewer's sheet: `python3 antweb_types/refresh_typestatus_sheet.py SHEET.xlsx OUT/ protonyms.jsonl protonym_flags.jsonl aw.tsv OUT/typestatus_merged.csv`
7. NGC labels: `python3 bolton/ngc_labels.py protonyms_species_typeinfo.jsonl.gz OUT/ngc_labels_draft.csv`
8. His week: `python3 antweb_types/typestatus_week.py --merged OUT/typestatus_merged.csv --adds OUT/primary_adds.csv --held OUT/primary_adds_held.csv --labels OUT/ngc_labels_draft.csv --protonyms protonyms.jsonl --out WEEK/`,
   then `python3 bolton/review_week.py --spec WEEK/week.json --xlsx WEEK/week.xlsx`.

## June 2026 results (8 Jun exports)

The June README's numbers stop at its last edit in turn 35. This table has the final figures
from the chat.

| | |
|---|---|
| AntWeb type specimens | 36,108 |
| already on AntCat (code in a protonym's type fields) | about 10,000 |
| not on AntCat | 25,823 (after the spaced-code fix) |
| routed to one protonym (`auto`) | 22,177 |
| primary-type additions | 8,675 protonyms (see below) |
| rank disagreements (holotype vs paratype) | 207 |
| misplacements (code under another protonym) | 223 |
| material-kind conflicts on additions | 1,524 (1,271 are AntWeb syntype vs AntCat holotype) |
| AntWeb type_status name fixes | 426 (387 current combination, 39 spelling); the June README's 772 is from before turn 39 |
| species-group protonyms with a type specimen code | 37.6% now, 67.6% after the merge (of 24,295) |
| current valid species-group names with one | 41.3% now, 73.6% after the merge (of 16,964) |

The 8,675 primary-type additions break down as:
- 6,958 add a specimen line;
- 1,071 append to an existing specimen line;
- 438 add a depository line;
- 208 full blocks.

## 8 Nov 2026 results (8 Nov exports, after commits eca9815 and fdae8b9)

| | |
|---|---|
| AntWeb type specimens | 36,594 |
| already on AntCat | 10,453 |
| not on AntCat | 25,983 (auto 22,297, ambiguous 7, no match 3,679) |
| additions | 8,611 protonyms: specimen line 7,334, append 1,133, full block 126, depository line 18 |
| held by convention | 104 (replacement name 68, by history text 17, nomen nudum and/or unavailable 19) |
| material flags | 1,585 |
| present_check (code already in AntCat) | 81 protonyms |
| additions on records with NGC-style labels | 408: relabel those first (`bolton/ngc_labels.py`) |
| misplacements / rank / AntWeb name fixes | 158 / 205 / 431 |

June's "438 add a depository line" was mostly the NGC-label fault: those records already name a depository.

## Decisions settled with Brian in June (do not regress; `selftest.py` checks them)

- **Codes.** Match by specimen code, ignoring case and punctuation. AntCat's "AMNH Bu-014" is
  AntWeb's amnh-bu014.
- **Code format on entry.** Enter the bare AntWeb code in uppercase (`AMNH-BUFB80`); AntCat links
  it on save. Use the URL only for a code that will not link.
- **Locality.** Never write a locality taken from AntWeb; it comes from the publication.
- **Full blocks.** A full block (no type text on AntCat) gets material, depository and specimen,
  plus a secondary block when AntWeb has paratypes.
- **Material conflicts.** These are flagged in `material_flag`; the specimen link is still
  added.
- **Name comparison.** Compare genus and last epithet only. Subgenera, connecting words (r., var.,
  st.) and gender endings are not fixes.
- **Spelling fixes.** For `spelling` rows, which side is right is not known (sylvaini/silvaini).
  Check the original description. Brian: keep them in the list as they are.
- **Bare type_status.** A bare "holotype" routes through the determination when that name is
  itself a protonym.

## Still to do before anything is written to AntCat

- **No write runner exists yet.** A write goes through the Protonym model as AntCatBot, with the
  staged gates in CLAUDE.md: snapshot, dry run, canary checked in the live UI, about 10 rows,
  then the rest. Primary types first.
- **Done 2026-11-03: primary and secondary text are split.** The `primary_add` and
  `secondary_add` columns hold the text for `primary_type_information_taxt` and
  `secondary_type_information_taxt`. `add_text` is kept as in June.
- **Done 2026-11-03: AntCat's conventions are applied** when `--flags` is given. Protonyms with no
  type information by convention go to `primary_adds_held.csv` with a `hold_reason`: nomina nuda,
  replacement names, unavailable names, and quadrinomials to check.
  - The runner `export_protonym_flags.rb` has been syntax-checked and its fields checked against
    AntCat's schema. It has not yet been run on a server: run it on staging first.
- **Done 2026-11-03: depositories are checked** when `--institutions` is given. `depository_check`
  flags AntWeb `ownedby` values that are not AntCat codes, and names the AntCat code when an
  `[Also]` note links them (AntWeb INBC = AntCat INBio).
- **Material list.** `review_material_mismatch.csv` from June came from an inline step that was
  not kept. The same flag is the `material_flag` column of `primary_adds.csv`.
- **Rerun first.** Rerun on fresh exports before any review. Done 2026-11-08 (above).
- **Relabel before linking.** 408 additions sit on records with NGC-style labels. Agree the
  wording with Bradley, relabel (AntCatBot, staged), rerun, then write the specimen codes.
- **reconcile_types.py code regex** misses spellings like "USNM# 609605" and does not read type
  notes; `present_check` in build_inserts.py catches these for now. The June rule is "match by
  code, ignoring case and punctuation": widen the regex (with a selftest case) before the misplacement
  and rank lists are trusted for such codes.

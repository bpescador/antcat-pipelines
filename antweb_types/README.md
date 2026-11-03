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
   `docker exec -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/export_protonyms.rb`.
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
4. `python3 antweb_types/build_inserts.py protonyms_species_typeinfo.jsonl aw.tsv OUT/type_link_queue.csv OUT/`
5. Before trusting a run after any code change, `python3 antweb_types/selftest.py` must print
   SELFTEST PASS. `smoke.sh` runs it too.

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
- **Full blocks need splitting.** A full block's `add_text` holds the secondary block in the same
  string. On a write it goes into `secondary_type_information_taxt`, not the primary field.
- **AntCat conventions found in the October depository work are not applied.** AntCat gives no
  type information under replacement names, nomina nuda, or quadrinomials whose name was later
  used at another rank. Filter these before any list reaches a reviewer. The export carries
  `nomen_nudum`.
- **Depositories.** A depository comes from AntWeb `ownedby`, which is sometimes a name, not a
  code ("SMNS Stuttgart"). Check against antcat.org/institutions.
- **Material list.** `review_material_mismatch.csv` from June came from an inline step that was
  not kept. The same flag is the `material_flag` column of `primary_adds.csv`.
- **Rerun first.** Rerun on fresh exports before any review. The June lists are five months
  stale, and the depository work has since changed AntCat.

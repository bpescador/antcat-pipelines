# AntCat → TaxonWorks DwC-A checklist import — team runbook

How to build and test a Darwin Core Archive checklist to add missing AntCat
names to a TaxonWorks project, and the traps that will bite you if you don't.
Written against TaxonWorks build **`96f69237a`** (2026-07-10, `sandwich`).
Supersedes `ae0829d1b`, on which the checklist importer crashed on empty
`originalNameUsageID` (see [worked example](#worked-example)).

For the importer as a TW concept:
<https://docs.taxonworks.org/guide/Manual/import.html>

> **The single most important rule:** the checklist importer has **no undo**.
> It creates real TaxonName records that you cannot bulk-delete afterwards.
> Every run goes to a sandbox first, and never to production until a corrected
> run has been verified in a clean sandbox project. See
> [No undo](#no-undo-the-rule-everything-else-serves).

---

## Contents

1. [The three-source setup](#the-three-source-setup)
2. [No undo — the rule everything else serves](#no-undo-the-rule-everything-else-serves)
3. [Which project to import into, and the one setting that decides everything](#which-project-to-import-into-and-the-one-setting-that-decides-everything)
4. [Building the file: reference closure](#building-the-file-reference-closure)
5. [Building the file: status vocabulary](#building-the-file-status-vocabulary)
6. [Building the file: the parse traps](#building-the-file-the-parse-traps)
7. [Exporting TW names to diff against (the 10k clamp)](#exporting-tw-names-to-diff-against-the-10k-clamp)
8. [The protonym key](#the-protonym-key)
9. [Upload: delimiter dialog](#upload-delimiter-dialog)
10. [Reading the result: NotReady / Failed / Errored](#reading-the-result-notready-failed-errored)
11. [Verifying against specimens](#verifying-against-specimens)
12. [Exporting just the names this import created](#exporting-just-the-names-this-import-created)
13. [What you can't do today](#what-you-cant-do-today)
14. [Separate, pre-existing: Combinations with `[GENUS NOT SPECIFIED]`](#separate-pre-existing-combinations-with-genus-not-specified)
15. [Open issues to track](#open-issues-to-track)
16. [Worked example](#worked-example)

---

## The three-source setup

Three catalogues, each authoritative for a different thing:

- **AntCat** — authoritative for ant nomenclature. The names you want to add.
- **TaxonWorks** — the project you're reconciling. May lag AntCat.
- **Specimen determinations** — names your collection objects actually use.
  A determination can point at a name that has no TaxonName record behind it.

The reconciliation produces four review lists (`tw_missing`, `tw_status_differs`,
`tw_extra`, `unresolved`). Only `tw_missing` feeds the importer. The importer
**inserts only — it never updates**, so `tw_status_differs` is a manual worklist,
not something the importer can touch.

---

## No undo — the rule everything else serves

A checklist import creates `TaxonName` records. There is no rollback:

- **Deleting the import dataset does NOT delete the names.** `dataset_records`
  are `dependent: :delete_all` — that removes the staging rows only. Every
  TaxonName the run created stays.
- **There is no batch destroy for taxon names.** The controller has `batch_load`
  and `batch_update`, no batch delete.
- **Manual deletion is leaf-first and blocked by relationships.**
  `check_for_children` refuses to delete any name with children
  ("delete those first"); synonym relationships are `restrict_with_error`.
  Deleting ~660 names by hand is not feasible.

Consequence: **one wrong run can create hundreds of names you cannot practically
remove.** On a sandbox this is an annoyance ("all data may be deleted at any
time"). On production, against the team's "no deletions, ever" rule, it is a
standing mess. This is why every import is sandbox-first.

---

## Which project to import into, and the one setting that decides everything

The Settings dialog has a checkbox:

> `use_existing_taxon_hierarchy` — *"Taxon names without parentNameUsageID will
> match existing nomenclature instead of being children of Root"*

It governs the one row in the file with a blank `parentNameUsageID` — the root
(`Formicidae`). Its correct value is the **opposite** in the two situations you'll
be in:

| Situation | Setting | What the root row does | Why |
|---|---|---|---|
| **Empty/new project** (format test) | **OFF** | becomes a child of Root | nothing exists to match; ON would error "no TaxonNames matched" |
| **Existing project** (real target) | **ON** | matches the existing Formicidae | OFF would create a **second** Formicidae and rebuild the whole tree under it |

**The failure that taught us this:** importing into a project that already had
Formicidae, with the box OFF, created a duplicate `Formicidae` under Root and
~660 duplicate descendants — a parallel classification. Nothing matched; every
child resolved its parent to the new duplicate. (This is GitHub #4249.)

When the box is ON in an existing project, the root row matches by **name**
(`name` + `cached` + `rank_class` + `verbatim_author` + `year_of_publication`),
not by id. If your Formicidae stores its author via a role rather than
`verbatim_author`, the match returns nothing and the root row Errors; the fix is
to blank `scientificNameAuthorship` + `namePublishedInYear` on that one row.

**Residual risk even with the box ON:** every non-root row still resolves its
parent from *within the file*, and that parentage comes from the source export.
Anywhere the TW hierarchy has drifted from the source (a genus moved tribe, say),
that node still duplicates. After any real run, re-check a known genus
(e.g. `Camponotus`) has exactly one record with its full descendant count and OTUs.

---

## Building the file: reference closure

The importer resolves `parentNameUsageID`, `acceptedNameUsageID`, and
`originalNameUsageID` **only against taxonIDs present in the same file** — never
against TaxonWorks ids. Validation (`checklist.rb`):

```
No record with taxonID <id> found in dataset
```

So the file must be **reference-closed**. To add N leaf names you must also
include:

- every ancestor up to the root (`Formicidae`), each as its own row;
- the **parent species** of every new subspecies (subspecies parent = species,
  not genus);
- the **senior** (accepted name) of every synonym/homonym leaf.

These "support rows" are names that already exist in TW. They are present only to
satisfy references; with `use_existing_taxon_hierarchy` ON they match rather than
duplicate. A 462-name add expanded to ~706 rows once closure was satisfied.

You cannot substitute a TW `taxon_name_id` for a support row — the importer has no
field that means "this is a TW id." (Being able to is the open request #3830.)

---

## Building the file: status vocabulary

`taxonomicStatus` drives two mutually exclusive paths. Get the pairing wrong and
the row errors.

**`acceptedNameUsageID` points at ANOTHER row** — status must be one of:
`synonym`, `homonym`, `misspelling`, `original misspelling`, `invalid`.

**`acceptedNameUsageID` points at ITSELF** — status must be one of:
`valid`, `accepted`, `invalid`, `unavailable`, `excluded`, `nomen nudum`,
`ichnotaxon`, `fossil`, `nomen dubium`, `incertae sedis`.

AntCat→DwC status mapping used:

| AntCat `status` | DwC `taxonomicStatus` | Path |
|---|---|---|
| valid | valid | self |
| synonym | synonym | → senior |
| homonym | homonym | → senior (needs one!) |
| unavailable | unavailable | self |
| unavailable misspelling | misspelling | → senior |
| excluded from Formicidae | excluded | self |
| unidentifiable | **nomen dubium** | self (see note) |

**`unidentifiable` → `nomen dubium` (curatorial mapping, agreed for AntWeb).**
AntCat's `unidentifiable` has no direct DwC/TW status. We map it to
`nomen dubium`, which the importer accepts and files as
`TaxonNameClassification::Iczn::Available::Valid::NomenDubium` (self-referential —
`acceptedNameUsageID` = the name itself). Rationale: AntCat uses "unidentifiable"
for available names whose application can't be determined (per Fisher 2025,
*Replacement names for junior homonyms in ants*, suppl. E2 — junior homonyms left
unreplaced "because the status ... is unidentifiable"), and AntCat's own catalog
pairs "unidentifiable taxon" with "nomen dubium." This is a **curatorial decision,
not a mechanical equivalence** — "unidentifiable" and "nomen dubium" are not
strictly synonymous in the Code (dubium implies *available but doubtful*), so a
name that is actually unavailable should not be forced here. For AntWeb's current
cases (e.g. `Iridomyrmex bicknelli luteus`, `Tetramorium caespitum barabense`)
`nomen dubium` is the agreed target.

**`homonym` must carry its replacement name.** A junior homonym is invalid and is
replaced by another name; the importer maps `homonym` + `acceptedNameUsageID` →
`TaxonNameRelationship::Iczn::Invalidating::Synonym::Objective::ReplacedHomonym`.
AntCat records the replacement (e.g. `Camponotus substitutus clarus` Stitz 1938 →
`Camponotus substitutus cylrix` Fisher 2025), but earlier exports left
`valid_name` blank for homonyms — an **export gap, not a real absence**. A homonym
arriving with no replacement is a signal to fix the export upstream, not a name to
drop. Only a homonym AntCat *genuinely* can't resolve goes to `unresolved`.

**Resolve the replacement against the import batch, not just the reference file.**
Homonym replacements are frequently *themselves* new names (the Fisher 2025
replacement set — `cylrix`, `chucki`, `dazia`, `hector` …), so they won't be in an
older DwC reference file. The builder must accept a replacement whose row is a new
leaf created in the same import (matched by `valid_name_id`), or it will wrongly
exclude the homonym. In the current run this recovered 4 of 5 missing homonyms;
the 5th failed only because its replacement's *genus* was itself absent.

The `Fossil` flag rides in its own column: **`TW:TaxonNameClassification:Iczn:Fossil`**
= `true`. This is one of only four `TW:` columns the importer reads.

---

## Building the file: the parse traps

Deriving the protonym key from `original_combination` (TW side) and building DwC
fields hit three real parse bugs. All three are silent — they produce a wrong key
or a malformed field, not an error.

- **`[sic]` mid-string.** TW writes `Genus [sic] epithet`; a leading-bracket
  stripper leaves `sic` as the epithet. Strip **all** `[...]` interjections,
  anywhere in the string.
- **Capitalised author particles.** `parse_protonym` demotes lowercase particles
  (`de Andrade` → `andrade`) but not capitalised (`De Andrade` → keyed as `de`).
  Lowercase capitalised particles after the first token before keying. This alone
  caused ~100 false "missing" names.
- **HTML in authorship.** AntCat `authorship` carries markup
  (`Ulysséa <i>et al.</i>, 2015`). Strip tags and unescape entities before it
  goes into `scientificNameAuthorship`, or you create protonyms with `<i>` in the
  author. (`&` alone is fine — the reference file uses it.)

### `spelling_differs` and `originalNameUsageID`

Names where AntCat's original combination differs from the current spelling
(gender agreement, later transfer) should carry an `originalNameUsageID` pointing
at an obsolete-combination row, so TW records the true original spelling. If you
leave it **blank**, TW builds the protonym with the *current* gender-agreed
epithet as the original — nomenclaturally wrong for these names.

Two cautions:

- On builds **before `96f69237a`**, a blank `originalNameUsageID` didn't just lose
  the original spelling — it **crashed** the row to `Failed` (unguarded nil;
  CHANGELOG: *"Checklist importer crashing on empty originalNameUsageID in some
  cases"*). This was the cause of the 20 Failed rows in the worked example. The
  file was correct; the importer was not nil-safe. Fixed in `96f69237a`, which
  now turns the empty field into a clean `Errored` instead.
- Even with the fix, a blank `originalNameUsageID` still records the wrong
  original spelling. The proper fix is to generate obsolete-combination rows for
  each `spelling_differs` name and point `originalNameUsageID` at them. Until
  then, these names import but their original combination is approximate — a known
  refinement, not a silent error.

---

## Exporting TW names to diff against (the 10k clamp)

Filter Nomenclature's CSV download is **silently capped at 10,000 rows**
(`Kaminari.config.max_per_page = 10000`) AND builds the CSV client-side from the
rows loaded in the browser. Setting `per=30000` in the URL still returns 10,000,
the screen shows 10,000, the CSV holds 10,000 — **no warning**.

**Workaround:** paginate. The list is `id`-ordered and stable, so pull
`page=1`, `page=2`, `page=3` at `per=10000` and stitch. Verify: the pages should
have contiguous non-overlapping id ranges summing to the record count shown in the
filter header.

Minimum columns needed for reconciliation:
`id, name, rank, type, cached, cached_original_combination, cached_author_year,`
`year_of_publication, cached_is_valid, cached_valid_taxon_name_id, cached_misspelling`.
(Filter Nomenclature's export labels differ; `original_combination`,
`cached_is_valid`, `valid_name` are the essentials.)

---

## The protonym key

Match names on **protonym identity**, never on current spelling:

```
original_genus | original_epithet | first_author_surname | year
```

- Derive `original_genus` and `original_epithet` from the **original combination**
  (first token = genus, terminal token = epithet), not the current name.
- **The author is required in the key.** A 3-part key (`genus|epithet|year`)
  silently conflates homonyms — two authors, same epithet, same year. TW may hold
  both members of a pair even when AntCat holds one. Dropping the author produced
  false matches in the first 37% of the data.
- Any key that collides (within TW, or against AntCat) goes to `unresolved` — it
  is an unknown, never a guess.

---

## Upload: delimiter dialog

The upload dialog **defaults to Comma**. Our files are tab-delimited.

| Field | Value |
|---|---|
| Field delimiter | **Tab** |
| String delimiter | **None** |

`None` is safe only if the file has no quote characters. The build script emits
LF line endings, no quotes, no carriage returns, no ragged rows — verify before
upload if hand-edited.

---

## Reading the result: NotReady / Failed / Errored

The status counts mean different things. Two are normal; two are not.

- **NotReady (normal).** On load, a row is `Ready` only if it has no error, no
  dependencies, and no parent — i.e. only the root. Everything else is `NotReady`
  until its parent imports. This is a topological cascade
  (Formicidae → subfamily → tribe → genus → species → subspecies). You may need
  to press **Import** more than once to walk all levels. Watch Imported climb and
  NotReady fall.
- **Errored (data problem, visible).** Row failed validation — bad status
  vocabulary, unresolved reference. The reason shows in `error_data`. Fixable in
  the file.
- **Failed (crash, INVISIBLE).** An unhandled Ruby exception. The message and
  backtrace are written to `metadata[:exception_data]` but **never surfaced** —
  not in the UI, the JSON, or Download table (this is #2808). You cannot see why
  from the workbench.
- **Failed is terminal (pre-`96f69237a`).** No retry path selected it — not the
  Import button, not "retry errored," not per-row import; the only recovery was a
  fresh import dataset. Note the crash that produced our 20 Failed rows (empty
  `originalNameUsageID`) is fixed in `96f69237a`; SFG's redeploy also flipped the
  stuck rows back to Ready so they could be retried in place. **This fix is on
  sandboxes only — production/practice get it next release.**

**The stall signature to watch for:** `Ready: 0` with `NotReady > 0` and no further
progress means something upstream Errored/Failed and never unlocked its children.

**Diagnosing a Failed batch (needs console):** ask SFG to run
`DatasetRecord.where(import_dataset_id: <N>, status: 'Failed').pluck(:metadata)`
and read `exception_data`. Leave the dataset live — deleting it destroys the
evidence (and doesn't remove the imported names anyway).

---

## Verifying against specimens

The taxon-name export can miss names that specimens actually use. Cross-check the
import list against a specimen occurrence export (`genus`, `specificEpithet`,
`infraspecificEpithet`, `scientificNameAuthorship`):

- **Same name + same author** as a name you're importing → confirms the name is
  needed (the specimen determination has no TaxonName behind it). Import it.
- **Same name + DIFFERENT author** → a homonym or a specimen misID. Different
  name; send to `unresolved`, do not silently merge.

In one run this surfaced 70 names on 191 specimens that were determined but had no
protonym in the project — all with matching authorship, all legitimately missing.
The specimen export is a projection (no `taxonID`), so it confirms *need*, not
*identity*; treat name+author agreement across AntCat + specimen + absence-from-TW
as the signal.

---

## Exporting just the names this import created

After a run you'll want the set of names *this* import added — for review or a
record. Three handles, in order of reliability:

- **Import data attribute — DO NOT rely on it alone.** Every name any DwC-A import
  creates is stamped with an `ImportAttribute` predicate `DwC-A import metadata`.
  In a project with a prior migration this catches **all** of them (23k+), not
  your run — the stored value is a broken serialization (the importer's own
  comment: *"Will not serialize properly"*), so it carries nothing to distinguish
  one import from another. Filtering on it returned the whole project, not the run.
- **Created/updated date window — usable, imperfect.** Filter Nomenclature inherits
  a housekeeping facet (`created_by`, `updated_since`, date range). Set
  `updated_since` to just before the run and `created_by` to yourself. Caveat: the
  cascade creates subspecies *last*, minutes after the species, so a window that
  starts too late clips the tail (in one run this returned 353 of ~438 — the
  subspecies were the ones missing). Push the start time back and re-pull.
- **Import dataset id — the only exact key.** Each created name links back through
  its `DatasetRecord` to the import dataset. Scoping by that id gives precisely the
  names from one run, regardless of timing. There is **no Filter Nomenclature facet
  for this today**, so it's a console query (or a Matt question):
  `DatasetRecord::DarwinCore::Taxon.where(import_dataset_id: <N>, status: 'Imported')`
  `.map { |r| r.metadata.dig('imported_objects','taxon_name','id') }.compact`.
  Worth requesting as a filter facet — verifying "what did this import add?" has no
  clean UI path.

Whatever the method: the 10k export clamp still applies. Verify the count matches
the run's new-name total before trusting the file.

---

## What you can't do today

- **Undo an import.** No rollback, no dataset-level delete of created names.
- **Bulk-delete taxon names.** Leaf-first only, relationships block.
- **Use a TW id as a parent** in the checklist (#3830).
- **See why a row Failed** from the UI (#2808).
- **Update an existing name's status** via the importer — insert only. Status
  reconciliation (`tw_status_differs`) is a manual worklist.
- **Export >10,000 names** from Filter Nomenclature in one pass — paginate.
- **Isolate one import's output by data attribute** — the import predicate is
  shared across all DwC-A imports; use the import-dataset id (console) instead.
- **Patch a genus onto an existing Combination** through a clean UI gesture — the
  New Combination task doesn't cleanly support it (see the Combinations section).

---

## Separate, pre-existing: Combinations with `[GENUS NOT SPECIFIED]`

**This is 2023-migration debt, NOT produced by this import — but you will see it,
so know what it is and what not to do.**

The 2022/2023 DwC-A migration created **Combination** records (historical
name-usages) from AntCat's obsolete-combination rows. Where a combination has a
**subgenus** but the migration never wired up the **genus** relationship, TW
renders `[GENUS NOT SPECIFIED]` and raises a soft-validation flag
("...in combination requires selection of genus"). ~15 exist on production.

- **It is cosmetic, not an integrity problem.** The valid name resolves correctly;
  parents and synonymies are intact. Nothing is broken.
- **The genus is unambiguous** — it is the parent shown in the record
  (`Camponotus` for the *Dendromyrmex*/*Phasmomyrmex* ones, `Crematogaster` for the
  *Acrocoelia*/*Orthocrema* ones).
- **DO NOT delete them.** These Combinations anchor **OTUs that carry specimen
  determinations** (Coordinate OTUs, distributions, images). Deleting strands
  specimens, and removes real nomenclatural history that AntCat would re-sync anyway.
- **DO NOT use "Edit OTU"** to change the name — that re-points the OTU, wrong door.
- **The fix is non-obvious.** It means adding the genus element to the existing
  combination. The **New Combination** task is built for *creating* combinations,
  warns it's "only configured for ICZN names," and does not cleanly patch an
  existing one. Treat this as a **question for Matt / possible console fix**, not a
  routine curation gesture. Fix ONE and confirm the placeholder clears before doing
  the rest.

**Why this import doesn't add more:** the AntCat checklist file contains **zero
combination rows** — AntCat's obsolete-combination rows were excluded at source, and
the 462 names are all Protonyms. The importer only creates a Combination from a
combination row, so this run produces none. *This guarantee holds only as long as
the file contains no combination rows* — a future file that included AntCat
obsolete combinations would reproduce this unless it specified the genus.

---

## References & citations — the AntCat → TW linking workflow

Moving names from verbatim author/year to linked citations. Verified end-to-end on
staging (build `96f69237a`) except the final bulk write (Matt/console).

### The forced sequence (the checklist importer consumes no citation field)

TW's DwC-A checklist importer reads no source/citation column, so references cannot
be linked at name-import time. The order is forced:

1. **Load references as Sources** (BibTeX batch-load).
2. **Names already exist** (verbatim author/year) — on production most do; nothing to
   re-import.
3. **Link** names to Sources in a separate pass, keyed by id.

### AntCat export pipeline (canonical)

The AntCat side is now correct-by-default — one command, self-validating, no
hand-patching:

```
./build_tw_exports.sh <worldants.txt> <antcat_references.csv> [out_dir]
```

It runs both generators (names TSV + references BibTeX) and strict-validates before
exit: strict parse of every entry, crossref targets all present, `reference_id →
BibTeX` = 100%. It **exits non-zero on any failure**, so wired into a pipeline it stops
rather than emitting a bad file. Canonical scripts: `export_references.rb` (container
resolution built in — the former `_v2`) and the BibTeX generator with the fixed
escaper. Name export emits all four join columns by default (`valid_name_id` col 12,
`target_kind` 13, `reference_id` 18, `reference_pages` 19); positions 1–17 unchanged.

Next cycle: run `export_references.rb` on the droplet → pull CSV + dump → run
`build_tw_exports.sh` → correct `.bib` + `.tsv`, no manual steps.

**The escaper fix (durable, and why library-alone fails).** BibTeX field values are
brace-delimited, so you must NOT backslash-escape `{`/`}` inside them (`\{` is not
balanced to BibTeX-Ruby, and TW's parser errors at the *next* `@`, so one bad title
kills the load). The fix (`bib_value`) **balances braces first — keeps balanced pairs,
drops unmatched `{`/`}`, strips stray backslashes — then emits.** `[` `]` left alone
(legal; editorial brackets stay); `&%$#_` untouched (literal inside braces). Critical
finding: a serializer library (`bibtexparser`) is NOT sufficient on its own — its
writer *silently dropped* a mismatched-brace entry rather than erroring. Source strings
with genuinely unbalanced delimiters must be sanitized BEFORE any serializer. Sanitize,
then emit.

**Validate the *generated* file before every load** (their pipeline check and TW's
parser are both BibTeX-Ruby-ish but have diverged before): strict-parse all entries,
confirm crossref closure and 100% `reference_id → key` join. Do this on the file the
pipeline produced, not a hand-patched one.

### Loading references (BibTeX batch-load)

- **Convert AntCat references to BibTeX** carrying the AntCat reference id as the
  **citation key** (`@article{antcatNNNN, ...}`). Nested works (`@incollection`) use
  `crossref = {antcatCONTAINER}` **plus an explicit `booktitle`/`editor`** — TW does
  NOT resolve crossref inheritance, so the explicit container fields are load-bearing,
  not redundant.
- **Escaping trap:** literal braces/brackets in a title must be *stripped*, not
  backslash-escaped. `{`→`\{` inside a braced BibTeX value is invalid and the parser
  504s/errors at the next `@`. (Bit 4 titles in the AntCat export.)
- **Namespace is mandatory, and it is THE decision.** At the batch-load form, select a
  namespace (e.g. `antcat_ref`) in "Namespace for BibTeX labels." This turns the
  citation key into a queryable `Identifier::Local::Import::Bibtex` on each Source.
  Without it the id lands only in `key`/`note` and **is not searchable** (see below).
  Namespace settings: verbatim blank, is_virtual unchecked, delimiter None.

### The 504-on-success trap (verify by count, never by the screen)

- **Preview scales; Create does not.** Preview renders fine at 2,000 entries. **Create
  504s** at that size — but the Sources ARE written (the timeout kills the *response*,
  not the transaction). A successful load looks like a failure.
- **Chunk to ~2,000 entries**, split so every `@incollection` travels in the same file
  as its `crossref` container (no dangling crossref, no entry in two files).
- **Verify each chunk by the Source "Created by user" count rising by exactly the chunk
  size.** Never retry a chunk that already counted — the loader does NOT dedup, and
  there is no bulk source delete, so a re-load creates duplicates you cannot remove.
- **For production, ask SFG to run `Source.batch_create` on the console** — it does the
  identical write with no HTTP request to time out. Seven manual chunks against
  production (load-once, no undo) is exactly where server-side loading is safer.

### Finding the loaded id afterwards (the non-obvious part)

The AntCat id is carried in three places on each Source, but only ONE is queryable:

| Field | Queryable? |
|---|---|
| Verbatim keywords (`antcat_id=NNNN`) | **No** — inert free text |
| Note (`antcat_id: NNNN`) | **No** |
| **Identifier** (`antcatNNNN`, via namespace) | **Yes** |

To find/filter by the id: **Source Filter → Identifiers facet → enter `antcatNNNN`
(Partial) AND select the `antcat_ref` namespace.** Keyword search will NOT find it;
the note will NOT find it. For bulk, use the **"matching identifiers"** facet (Type:
Identifier, `\n` delimiter) — paste the whole list of `antcatNNNN` values at once.

### The linking join (deterministic, id-based)

```
TW taxon_name --protonym key--> antcat_names row --reference_id--> antcatNNNN
              --identifier--> TW source_id ;  reference_pages --> pages
```

Produces `taxon_name_id, source_id, pages` triples for ~100% of names. This sidesteps
the string-matching the built-in `verbatim_author_year_source` task uses (which breaks
on `Baroni Urbani`, `de Andrade`, `et al.`).

### Result (verified on staging)

**20,781 triples built** (`origin_citation_links.tsv`: `taxon_name_id, source_id,
pages, antcat_reference_id, protonym_key`). 0 duplicate taxon_name_ids; 99.3% carry a
page number; 3,643 distinct sources cited. **Both critical join legs were perfect: 0
AntCat rows lacked a `reference_id`, 0 `reference_id`s failed to resolve to a loaded
Source.** The ~1,850 non-linked names are the known `tw_extra`/`unresolved` set (in TW,
absent from AntCat) plus the `[sic]`/parse residue — not linking failures.

### The Source export drops the identifier column — recover from the cached note

The Filter Sources CSV export returns `id, serial, author, year, title, volume,
number, cached` — it does **NOT** include the `antcat_ref` identifier column, even
though that identifier is exactly what the join needs. Recovery: the `[antcat_id:
NNNN]` note is embedded in the `cached` string of every row, so extract it with
`antcat_id[:=]\s*(\d+)`. This is why carrying the id in three places (identifier +
note + keywords) at load time mattered — the one export that dropped the queryable
identifier still carried the note. Without that redundancy the join would have had no
anchor from a UI export. (File a request: Source CSV export should include identifier
columns.)

### Author mismatches are usually nested-chapter attribution, not errors

When a name's verbatim author/year disagrees with the linked Source's author, the
first instinct is "someone dropped an author." Usually it is the opposite: **AntCat
records the name at its CHAPTER-level authorship, which is a subset of the containing
work's authors** — and that shorter list is correct.

Worked example. *Aphaenogaster radchenkoi* and *A. maculifrons* were both published in
Kiran, Aktaç & Tezcan 2008 (Biológia 63). But each species was described in its own
nested chapter with its own authors: radchenkoi by Kiran, Aktaç & Tezcan; maculifrons by
Kiran & Aktaç; aktaci by Kiran & Tezcan. AntCat stores each name's chapter reference
(`@incollection`) with the chapter authors, `crossref`-linked to the container
(`@article`) that carries the full author list. So AntCat showing "Kiran & Aktaç" for
maculifrons is not a missing author — it is the actual describers of that species, and
the PDF confirms it ("*Aphaenogaster (Attomyrma) maculifrons* Kiran et Aktaç, sp. n.").

Method that settles these, in priority order: **the PDF is the truth; AntCat agrees with
the PDF; production agrees; a stale sandbox may not.** Check the original-description
heading in the PDF, confirm AntCat's chapter authorship matches, and treat any
disagreeing verbatim string as the stale side. In one audit of 50 flagged
verbatim-vs-source author differences, 37 were deliberate nested attribution (AntCat
correct), 12 were stale sandbox verbatim that self-resolves at production, and 1 needed a
PDF check that confirmed AntCat correct — **zero were AntCat missing an author.** Do not
"fix" AntCat to match a fuller verbatim string without checking the PDF; the fuller
string is often the container's author list, not the name's.

### The one unproven leg: the bulk write

Setting each name's origin citation has **no API path** (citation endpoints are
read-only), and the only native task (`verbatim_author_year_source`) is string-matched
and manual. So the id-based bulk write is a **console job** — hand Matt the triples and
ask whether there's a supported bulk path or it's a `Citation.create` loop. Test on
staging before production.

### PDFs (future, out of scope)

Attaching full-text is 12,955 individual binary uploads (no folder batch-load) — a
scripted per-Source job via API/console, driven by the same `antcatNNNN` identifier.
Far heavier than the reference load; correctly deferred.

---

## Open issues to track

- **#2808** — Failed records show blank; `exception_data` never surfaced in
  UI/JSON/export. The specific crash behind our 20 Failed is fixed in `96f69237a`
  (it now `Errored`s with a message); the general "Failed is invisible" gap may
  persist for other `StandardError` crashes — worth confirming.
- **#4249** — checklist duplicates the whole classification when the root already
  exists and `use_existing_taxon_hierarchy` is off; no load-time warning.
- **#3830** — request to use `taxon_name_id` as Parent ID (checklist-side of the
  Occurrence importer's `TW::TaxonDetermination::otu_id`).
- **#3687 / #4541** — prior `NoMethodError`/author-string crashes of the same
  Failed class.
- **#3669** — usability: warn when no root row has an empty `parentNameUsageID`.
- **AntCat export (upstream fix):** invalid names must carry their target id —
  homonyms were exported with a blank replacement (`valid_name`), which the
  reconciliation can't build a `ReplacedHomonym` from. Fix: export the
  replacement/senior name **and its antcat_id** for every non-valid status.
- **New (to file):** the 10,000-row Filter Nomenclature export clamp is silent;
  the CSV download exports the viewport rather than the filter result.

---

## Contribution strategy — getting fixes into TaxonWorks

Context for why this section exists: prioritizing through the weekly meetings and a
TaxonWorks Together talk did **not** get AntWeb's blocking fixes shipped. The commit
log and the community-consult notes explain why, and point to a different path.

### What the data shows

- **Commits are how work lands, and Matt is the bottleneck.** Last ~300 commits:
  Tom Klein ~97, jlpereira ~28, Hernán ~26, Matt (mjy) ~24. Matt — who runs the weekly
  meetings — is 4th by volume. Meetings/talks route through the scarcest coding
  resource; **merged PRs route around him** (anyone on the team can review + merge).
- **The PR model is the stated, intended contribution path.** From the consult notes:
  TW's model is *"your modules come to the TW as a pull request — 'here is my code,
  take it if you will.'"* Tom Klein built the most via fork PRs and is now on the team —
  demonstrated contribution is how you become central here.
- **SFG's real anxiety is review burden and untested code.** The notes openly ask *"do
  you really want people working on your code? … does our current model scale?"* The
  differentiator that makes a PR *welcome* rather than a burden is **visible testing** —
  the reproduction shown, the fix verified, ideally a spec. A plausible-looking
  (e.g. AI-generated-but-unverified) diff is exactly what they're wary of. Our
  discipline — reproduce on our own instance, confirm, show the test — directly answers
  that concern and is our edge.

### The path (in order)

1. **Stand up a local TW instance (Docker).** This is the prerequisite for everything
   below and the single highest-leverage change to how this work goes. It converts every
   blocker in this document — read-only API, invisible `Failed` exceptions, "is there a
   bulk write" questions, 504-babysitting — from "ask Matt and wait" into "test it
   ourselves and hand over working code." It would have let us read the 20 Failed
   exceptions directly, test `Citation.create`, and confirm `Source.batch_create`.
2. **Establish the contributor relationship with a small, tested PR first.** Model:
   Heidi Hopkins' docs PR (#124 in `taxonworks_doc`) — small, scoped, filed with "did I
   do this right?", reviewed and accepted. A docs or small-fix PR is the low-risk
   on-ramp before code PRs.
3. **Then submit code PRs for our blocking issues**, each with: the reproduction, the
   diagnosed root cause + line, the fix, and the cases tested. Ask for guidance as Heidi
   did rather than dropping a large diff.

### First code target: #4987 (typeStatus) — a real bug, patchable

Diagnosed from Michele's failing import (Kyle Gray Vanuatu Pheidole). Her `typeStatus`
values are `Holotype of Pheidole epaoensis` etc. In `parse_typestatus`
(`occurrence.rb:1214`): the string matches the `(\w+)\s+OF\s+(.*)` branch
(type=`Holotype`, name=`Pheidole epaoensis`), then must pass
`TypeMaterial.legal_type_type(code, type_type)` or it **raises `InvalidData`** and only
verbatim survives — exactly her symptom. Her file has **no `nomenclaturalCode` column**,
so `code` falls back to `import_dataset.default_nomenclatural_code`; if that default
isn't ICZN, `holotype`/`paratype` won't validate. Reproduce on the instance, confirm
which gate rejects it (default-code fallback is the prime suspect), patch, PR. Repro
data in hand.

### #4356 (roles) — an enhancement, not the same bug; likely a workflow fix first

Michele's file carries collector data in a **`roles`** column (+ the working
`TW:CollectingEvent:verbatim_collectors`). But the Occurrence importer has **no handler
for a bare `roles` column** — structured collectors are only created from
**`recordedBy`** (`occurrence.rb:886`, `parse_people(:recordedBy) -> collectors`). So
her parsed roles silently don't import while verbatim does. Two-part response: (a)
**immediate workaround** — put collectors in `recordedBy`, which may import them today
(emailed Michele to test); (b) **the actual enhancement #4356 asks for** — a `roles`
column supporting role types beyond plain collector — is a design conversation with SFG,
not a drive-by patch. Categorize it as enhancement, not "DwC broken."

### Framing to SFG (not "DwC is broken")

Verbatim data imports fine; specific *parsed/structured* fields don't. The accurate,
un-wavable-away statement is: *"the Occurrence importer drops parsed typeStatus (#4987)
and doesn't support a roles column (#4356), forcing hand-entry on every type
specimen."* Bring the blocking-5 as a prioritized cut of the 59 open AntWeb issues (10
on the priority list today — the other 49 don't signal urgency to SFG), with the
import-integrity cluster (#4987, #4356, #4329, #4101) flagged as blocking daily work.

### Known-and-unfixed items = leverage for the roadmap conversation

These are SFG-acknowledged workarounds, useful evidence that some friction is systemic,
not user error:

- **BibTeX batch load: ~2,000-entry chunks are the *documented* method** (consult
  notes: "we suggest you do batches, roughly 2000 at a time"). So the Create-504-on-
  success timeout is known and worked-around rather than fixed. Ask: fix the underlying
  synchronous-write timeout (background it like the DwC import job) so chunking isn't
  needed.
- **`unify` only moves related data in the *current project*** — cross-project
  dependents block deletion ("Cannot delete record because dependent collection objects
  exist"). Same architectural root as the no-bulk-delete pain in this document.
- **Silent 10,000-row export clamp** + Filter CSV exporting the viewport, not the
  result set.
- **`Failed` dataset records** store `exception_data` but never surface it (#2808) and
  can't be retried.

Each is a small, concrete ask; together they make the case that the import/export
tooling needs a focused pass for large-dataset users like AntWeb.

---

## Worked example

Two runs of the same 706-row file (462 new AntCat names + 244 support rows) on
`sandwich`:

1. **"Antweb July 2023" project, `use_existing_taxon_hierarchy` OFF** — the root
   (`Formicidae`) already existed, so with the box off it became a *second*
   Formicidae under Root and ~660 duplicate descendants were created. No undo; the
   duplicate subtree (`taxon_name_id 617169`) had to be left for a sandbox reset.
   Lesson: [the setting](#which-project-to-import-into-and-the-one-setting-that-decides-everything).

2. **Fresh empty project, box OFF (correct for empty), build `ae0829d1b`** —
   706 rows → 662 Imported, 0 Errored, **20 Failed**, 24 NotReady. The 20 Failed
   were spelling-difference names with a blank `originalNameUsageID` hitting an
   unguarded nil in the importer — a crash, not a file defect. The 24 NotReady
   were downstream of the 20.

   SFG (Hernán Pereira) shipped `96f69237a` — *"Fix empty originalNameUsageID
   crash on checklist importer"* — the same afternoon, rebuilt the sandbox, and
   reset the stuck rows to Ready. Re-running the **identical file** then gave
   **706 Imported, 0 Failed, 0 Errored, 0 NotReady.**

Takeaways: the file was structurally correct throughout; the failures were (1) an
operator setting and (2) an importer bug, neither a data-build error. Production
still runs the pre-fix build until the next release — do not run there until the
release ships and you re-verify on a sandbox running it.

*Also note the companion commit `1808cb1` — "Mark taxonRank ignored when otu_id is
used on occurrence import" — the Occurrence-side of `TW::TaxonDetermination::otu_id`.*

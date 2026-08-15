# Bolton NGC ⇄ AntCat sync — RUNBOOK v2

**Supersedes v1** (`BOLTON_SYNC_RUNBOOK.md`, written after the July 2026 Status-as-species run).

v1 documented one comparison (Status-as-species citations) end to end. It was correct for that
job. v2 generalises it, because by July 2026 three separate comparisons had been built — history
acts, Status-as-species citations, type material — and each one re-solved the same entity-matching
problems from scratch, in its own way, with its own bugs.

**What changed in v2**

1. A **resolve-once architecture**: entity resolution (references, protonyms, depositories) is
   extracted into a shared layer that every content comparison rides on.
2. An explicit statement of the **core asymmetry**: AntCat is queryable, NGC is not. This changes
   how the AntCat side should be read, and retires the habit of parsing the HTML dump.
3. **Bradley reviews residuals, never spaces** — made a rule, with the evidence for it.
4. Landmines found in the 2026 runs recorded in one place, including the author-normalisation trap
   that silently returns zero matches.
5. A **migration plan** with a parity test, so v2 can be adopted without a risky rewrite.

Companion docs (keep together): `LIVE_CONSOLE_FINDINGS.md` (AntCat data model — authoritative),
`ANTCAT_COMPARISON_MASTER.md` (all pipelines), `antcat_open_items.md` (changelog), and the
pipeline code bundle.

---

# 0. Core principles

Read this section before anything else. Everything downstream follows from it.

## 0.1 AntCat is queryable. NGC is fixed. Design around that.

This is the single most important thing to internalise, and it was under-used through the 2026
runs.

**The AntCat side is under your control.** You have root on the droplet and a Rails console. You
can write a runner that emits exactly the fields you need, in whatever shape you want, with the
data already resolved by the database. There is never a reason to regex structured facts out of
rendered HTML.

**The NGC side is whatever Barry sends.** ~596 Word files, prose paragraphs, formatting-as-
semantics (bold+italic marks a headword; italic marks a collector), inconsistent punctuation,
occasional legacy `.doc`. All parsing risk lives here. You cannot negotiate the format.

Consequences:

- **Never parse `worldants.txt`'s `taxonomic history html` for facts you can query.** The dump is
  a *rendering*. Rendering is lossy and regexes over it are approximate. In the July 2026 type
  work the first depository comparison was done by regex over rendered HTML and carried a
  "±a few percent" caveat that was purely self-inflicted — the same numbers came out exact once
  `export_protonyms.rb` supplied the real `primary_type_information_taxt` column.
- **Use `worldants.txt` only for what it is genuinely good at**: a fast, offline, whole-corpus
  snapshot for scoping and for joining on `antcat id`. Treat it as an index, not a source.
- **When you need a new field, write a new runner.** It costs one read-only round trip. That is
  cheaper than a week of debugging a regex that was never going to be exact.
- **Prefer the authority table to the inferred crosswalk.** The July 2026 type work first *derived*
  129 candidate depository code pairs from the data, planned a human review pass for them, and then
  discovered AntCat's `institutions` table already curated the synonymy in its `name` field as an
  `[Also …]` prefix. The whole review pass evaporated. Ask "does AntCat already store this?"
  before building machinery to infer it.

**Query cookbook** — see Appendix A.

## 0.2 Resolve once, compare many

Every content comparison needs the same three entities matched across the two catalogues:

| entity | the problem |
|---|---|
| **reference** | Bolton's `Kempf, 1972a` vs AntCat's `{ref 126357}` = `Kempf, 1972b`. Suffix letters are assigned independently. `X, in Y` vs `et al.` |
| **protonym / name** | Bolton records the name as published in its original combination; AntCat gender-agrees to the current genus |
| **depository** | Bolton's own 4-letter system vs AntCat's institutional codes: `BMNH` = `NHMUK` |

Resolve these **once**, into a versioned artifact, and let every comparison read that artifact.

**Why this matters more than it looks.** Measured on the 2026 catalogue: NGC's species blocks
contain **207,523 citation instances resolving to 6,031 distinct references — 34.4× amplification**.
`Bolton, 1995b` alone appears 21,488 times; `Kempf, 1972a` 5,521 times.

One mis-resolved reference does not produce one bad row. It produces ~34 on average, and thousands
for the heavily-cited catalogues. Under the v1 arrangement each pipeline resolved independently, so
every pipeline paid that multiplier again, and a fix in one did not fix the others. The `_canon_in()`
fix for `X, in Y` citations was applied to the added-refs diff and did not propagate.

Entity errors are the dominant error source in this project. Everything else is downstream.

## 0.3 Bradley reviews residuals, never spaces

Bradley Reynolds is the quality gate and his time is the scarcest resource in the pipeline. Protect
it with one rule:

> **Automated resolution runs first. Bradley sees only what it could not resolve, plus the content
> discrepancies that survive resolution. He is never handed an entity space to validate.**

Do **not** send him 6,031 references or 23,718 names to confirm. A reviewer with no stake in an
individual row reviews it worse than a reviewer looking at a row that matters — and the volume
guarantees fatigue. The July 2026 depository work is the shape to copy: 784 AntCat institutions plus
536 Bolton codes resolved automatically to 95.9%, and what reached a human was 21 errata, 6
institution gaps, and 740 content residuals. Nobody reviewed a crosswalk.

Corollary: **make the residual small before you send it, and sort it by whether action is even
possible.** In the type-depository sheet the 740 residuals split into 187 where NGC has something
AntCat lacks (actionable), 139 genuine two-way conflicts, and 414 where AntCat is simply more
complete than Bolton (almost certainly AntCat being right). Sending all 740 undifferentiated would
have spent more than half his effort confirming AntCat was already correct.

## 0.4 Staged writes, unchanged

The v1 write discipline was validated by a 565-row production run with zero errors. It is not
revised. See Phase 7.

---

# 1. Architecture

```
  LAYER 0   NGC PARSE                      (Barry's .docx -> structured records)
              |
              |  parse ONCE, emit structured fields, never re-parse block_text downstream
              v
  LAYER 1   ANTCAT EXTRACTION              (Rails runners -> exact structured exports)
              |
              |  query for what you need; never regex the HTML dump
              v
  LAYER 2   ENTITY RESOLUTION              (references / protonyms / depositories)
              |
              +---> entity EXCEPTIONS  -----> Bradley + Barry errata      [gate 1]
              |
              v
  LAYER 3   CONTENT COMPARISON             (acts, status citations, type material, ...)
              |
              +---> content DISCREPANCIES ---> Bradley                    [gate 2]
              |
              v
  LAYER 4   THE WRITE                      (dry-run -> snapshot -> canary -> batch)
```

Two review gates, not one. Gate 1 catches entity errors before they are amplified 34× into gate 2.
Under v1 there was only gate 2, so Bradley absorbed both kinds of problem in the same sheet, and
they look identical to a reviewer.

## Layer boundaries

**Layer 0 — NGC parse.** `parse_bolton.py`. Currently emits `block_text`, a newline-joined blob,
and every downstream script re-parses it its own way. **This is where format bugs multiply.** The
v2 target is one parse emitting structured fields per headword, with the source line preserved for
audit. Downstream scripts consume fields, never re-split prose.

**The schema is not a design decision — it is AntCat's data model.** The point of the parse is to
produce something comparable to AntCat, so AntCat's own storage defines the target. Do not invent
a schema from "what the comparisons need":

| NGC field | mirrors, in AntCat |
|---|---|
| `header` | protonym identity: original combination, author, year, rank, fossil flag |
| `acts[]` | `HistoryItem` rows — the 13 observed types in §2A, each with citations resolving to `{ref N}` |
| `type_block` | the three `Protonym` taxt columns, with sub-fields material / locality / depository / specimen (§2A) |
| `distribution` | `bioregion`, `country` |
| `notes[]` | `type_notes_taxt` for type notes; act-level notes stay attached to their act |

The only genuinely open work is the NGC-side **mapping**: how Barry's prose lands in those fields
(note-position convention, holotype/paratype split, formatting-as-semantics). That is parsing
against a known target, not schema design.

Layer 0 also owns **formatting recovery**. Barry encodes meaning in Word formatting, and
`p.text` discards it:

- bold+italic first run = headword (already used)
- **italic runs inside type lines = collector names**, which AntCat stores as `<i>…</i>`. Any
  pipeline that generates AntCat-format text from NGC needs these. Runs split mid-word
  (`'F. S'` + `'ikora'`), so merge adjacent same-format runs before emitting.

**Layer 1 — AntCat extraction.** Rails runners, read-only, one per concern. Existing:
`export_protonyms.rb` (type fields), `export_references.rb` (references + containers),
`institutions_export.rb` (institutions). Add runners freely; they are cheap and safe.

**Layer 2 — entity resolution.** Three resolvers, each emitting `matched` + `exceptions`. Status:

| resolver | current state | action for v2 |
|---|---|---|
| protonym identity | `protonym.py` — exists, shared, 99.2% match on 2026 data | keep; add author normalisation (§3.1) |
| reference matching | `citation_match.py` — exists but lives *inside* the status-refs pipeline | **extract to shared** |
| depository | built July 2026, lives in the type-material analysis | **extract to shared** |
| author normalisation | **does not exist as a shared component** | **build** (§3.1) |

**Layer 3 — content comparison.** One script per comparison, consuming resolved entities. These
already exist (`diff_history.py`, `diff_status_refs.py`, the type-material diff) and are the part
that should change least.

**Layer 4 — the write.** Unchanged from v1.

---

# 2. Procedure

## PHASE 0 — Inputs

1. **Bolton catalogue**: `AA_CATALOGUE_20XX.zip` (~596 files) from Barry, annual.
2. **AntCat structured exports** (Layer 1 runners — see Appendix A). Run them the same day.
3. **`worldants.txt` dump** — optional, for scoping and `antcat id` joins only.

> Filename trap: the dump has a literal dot before `worldants`. Unzip by exact name;
> `*-worldants_txt.zip` fails in zsh.

**Check for legacy `.doc` before parsing.** The 2026 bundle contained two:
`CAT-SPECIES CAMPONOTUS a-b.doc` and `SUB. 8 DEPOSITORIES OF TYPE-MATERIAL.doc`. `parse_bolton.py`
selects on the `CAT-SPECIES` filename prefix regardless of extension, so it **crashes** on these
rather than skipping them — and a crash in Camponotus a-b silently costs 217 headwords if the
traceback is ignored.

```bash
# detect
find <ngc_dir> -name '*.doc' -not -name '.*'

# convert (verified to preserve bold+italic headwords AND collector italics)
export HOME=/tmp
soffice --headless --convert-to docx --outdir <ngc_dir> <ngc_dir>/*.doc
# then remove or move the .doc originals so the prefix match doesn't pick them up
```

Verify after conversion: headword count and `Type-material:` line count should be non-zero, and
italic runs inside type lines should survive. For the 2026 Camponotus file: 217 headwords, 264
type-material lines, 236 italic runs.

## PHASE 1 — NGC parse (Layer 0)

```bash
python3 bolton_diff/parse_bolton.py <ngc_dir> bolton_out
```

Sanity-check the totals against last year. 2026 baseline: **23,718 species-group headwords**
(species 16,770, subspecies 6,271, infrasubspecies 677), 917 genus-group headwords, 6,115 reference
entries. A large drop usually means an unconverted `.doc` or a changed heading style.

## PHASE 2 — AntCat extraction (Layer 1)

Run the runners you need (Appendix A). Verify each against its own reported counts before moving on
— every runner should print what it wrote.

Transfer and integrity-check:

```bash
gzip -kf /var/www/antcat-2/tmp/<file>
md5sum  /var/www/antcat-2/tmp/<file>.gz
# on the Mac
scp root@<droplet>:/var/www/antcat-2/tmp/<file>.gz ~/Desktop/
md5 ~/Desktop/<file>.gz          # hashes must match
```

> `~/Downloads` is a Dropbox CloudStorage path and rejects writes. Use `~/Desktop` or `/tmp`.

## PHASE 3 — Entity resolution (Layer 2)

Run the three resolvers. Each emits matched pairs plus an exceptions file.

Record the match rates. 2026 baselines to compare against:

| resolver | rate |
|---|---|
| protonym key (NGC → AntCat) | 22,298 of 22,468 = **99.2%** |
| depository codes (after alias classes + Bolton list) | **95.9%** of comparable records |

A materially lower rate next run means something changed in the input, not that the catalogues
diverged. Investigate before proceeding.

## PHASE 4 — Entity exceptions → review [GATE 1]

Three products, each small:

1. **Barry errata** — NGC entities that resolve to nothing but are a single transposition or
   substitution away from a real one. 2026: 21 depository typos (`NMHB`→`NHMB` ×6,
   `NMHW`→`NHMW` ×3, `GNUK`→`GNUC` ×3, …). Disambiguate using the *other* side of the same record
   before asserting a correction; several codes resolve differently in different records.
2. **AntCat gaps** — entities Bolton has that AntCat's authority tables lack. 2026: `PMCT`
   (Princess Maha Chakri Sirindhorn Natural History Museum). Small curation items for Brian.
3. **Genuinely unresolved** — send to Bradley.

Fold confirmed corrections back into the resolution layer, then re-run Phase 3. The resolution
artifact is versioned; content comparison uses the post-review version.

## PHASE 5 — Content comparison (Layer 3)

Run the comparisons, consuming resolved entities. Each emits a review sheet.

**Sort every sheet by actionability before it leaves your machine.** Minimum: which side has the
extra information, and whether action on AntCat is even possible. See §0.3.

## PHASE 6 — Content review → Bradley [GATE 2]

Send the paper-level or category-level summary **first**, not the row-level sheet — paper is the
review unit, not 500 rows. Expect back:

- spelling/particle false positives → confirm already in AntCat, suppress
- hand-corrected AntCat ids for misspelling-target rows
- Bolton's own errors → these go to Barry as errata, **not** into AntCat

Watch for **blank corrected-id cells** — one slipped through in 2026 (Polyrhachis tyrannica) and
had to be resolved live in the console.

## PHASE 7 — The write (droplet)

**Unchanged from v1.** The data model is known; do not re-investigate, just verify.

### Settled facts (from `LIVE_CONSOLE_FINDINGS.md`, confirmed against production)

- **Mapping:** `Taxon.find(<antcat_id>).protonym.history_items`. History lives ONLY on the protonym.
- **Storage:** production Status lines are freeform `Taxt` blobs, not the repo's structured
  `StatusAsSpecies` type. `Status as species: {ref A}: p; {ref B}: p.`
- **Type fields** are three freeform taxt columns on `Protonym`, with labels stored *in* the
  string, not generated: `primary_type_information_taxt`, `secondary_type_information_taxt`,
  `type_notes_taxt`. Dominant label convention is `Primary type material:` /
  `Primary type locality:` / `Primary type depository:` (~29,000 records) with an
  NGC-style `Type-material:` minority (~1,600). Type notes use taxt markup (`{ref N}`, `{tax N}`)
  and are numbered `1) … 2) …` only when there is more than one.
- **Append** = insert `; {ref N}: page` before the trailing period. 49 lines lack a trailing
  period; add one.
- **Create** = `protonym.history_items.create!(type: 'Taxt', taxt: "…")`
- **Provenance:** AntCatBot, **user id 62**. Set `PaperTrail.request.whodunnit = 62`, and after
  `create_activity(event, User.find(62), edit_summary: …)` set `automated_edit = true` explicitly —
  nothing sets it automatically.
- **Guards the writer MUST include:** idempotency (skip if `{ref N}` already present);
  citation-shape precondition (`/\}:\s*[^;]+\z/`, else route to manual); one transaction per row
  covering write + Activity + flag; self-verify by reloading and comparing (`MATCH: YES`).

### The staged write (NEVER skip a gate)

1. **Dry run** — build every change, write nothing, log everything.
2. **DigitalOcean snapshot** (UI) — the gate before any commit.
3. **Canary** — one append + one create, verified in UI and Activity feed.
4. **Small batch (~10)**, verify.
5. **Full batch.**
6. **Manual rows** — resolve ref ids in console, confirm each.

### Required fixes before the next write run

Carried forward from the 2026 post-run review — **not yet implemented**:

1. **Chronology-aware insertion.** Split the line on `"; "`, resolve each `{ref N}` to its year,
   insert after the last segment with year ≤ incoming. Round-trip must be byte-identical or skip
   and flag. Same-year collisions flagged, never guessed.
2. **Process rows oldest-paper-first.** Sort the worklist ascending by year before writing.
3. **Dry-run chronology guard.** Flag every append where the existing line's last citation is newer
   than the incoming one. This single check would have caught all 21 misordered rows.
4. **Positioned creates (`insert_at`).** The canonical type order has now been **derived from
   production** — see §2A. Implement `insert_at` against that order. One question remains open with
   Bradley (`Replacement name` placement); until he answers, a create whose position depends on a
   `Replacement name` item should be **flagged for manual placement, not guessed**.

## PHASE 8 — Record & close

- Note the `EXECUTE_SCRIPT` marker Activity ids per write pass (2026: 249063, 249617, 249620).
- Archive `batch_write_log.csv`.
- Changelog entry in `antcat_open_items.md`: date, counts, marker ids, rollback path.
- **Record the residual counts** — see §5.
- Errata to Barry as a separate list, not mixed with batches he has already corrected.

## Rollback

Every write is paper_trail-versioned and attributed to AntCatBot. Reverse by filtering the Activity
feed on AntCatBot + edit_summary or the marker ids. Snapshot is the coarse fallback.

---

# 2A. History-item type order (derived from production, July 2026)

Needed for positioned creates (`insert_at`). `acts_as_list` scopes position to the protonym and
appends new items to the end, so a created item lands last regardless of convention — which is the
bug that misplaced two rows in the 2026 run.

## Method

The rendered `taxonomic history html` preserves `position` order. Extracted ordered item sequences
from **13,430 protonyms** holding ≥2 distinct types, normalised each item to a type label, built a
pairwise precedence matrix over **32,445 ordered observations**, and optimised the linear ordering
to minimise contradicted observations.

## The order

```
 1. First available use          8. Replacement name        <- position NOT confirmed
 2. Emendation/spelling          9. Status as species
 3. Also described as new       10. Junior synonym of
 4. Combination in              11. Senior synonym of
 5. Unavailable name            12. Material referred
 6. Nomen nudum                 13. Incertae sedis / unidentifiable
 7. Subspecies of
```

**94.1% of production pairwise observations are consistent with this order** (30,546 of 32,445).

Several edges are effectively absolute:

| rule | evidence |
|---|---|
| `Combination in` < `Status as species` | 6,842 : 0 |
| `Combination in` < `Subspecies of` | 2,559 : 0 |
| `Also described as new` < everything | 100% on all pairs |
| `Status as species` < `Senior synonym of` | 2,295 : 18 (99.2%) — **confirms Bradley's constraint** |
| `Unavailable name` < `Subspecies of` | 857 : 0 |

## What is NOT settled

`Replacement name` has **no stable position anywhere in production**:

| pair | split |
|---|---|
| vs `Status as species` | 207 : 193 (52%) |
| vs `Combination in` | 105 : 102 (51%) |
| vs `Subspecies of` | 88 : 86 (51%) |

That is the absence of a rule, not noise around one. Bradley's stated constraint ("Status as
species precedes Replacement name") is **not supported by the data** — pending his ruling, treat
`Replacement name` placement as unknown and flag rather than guess.

Also weakly determined, both low volume: `Incertae sedis` vs `Junior synonym of` (59%) and vs
`Status as species` (70%).

## Ruled out: chronological ordering

Tested whether items are simply ordered by citation year. Across 11,316 protonyms with ≥2 dated
items, only **50.1%** have non-decreasing years — indistinguishable from chance, and far below the
94.1% that type order explains. **History is type-ordered, not chronologically ordered.** Do not
re-litigate this.

(Note the contrast with citations *within* a Status-as-species line, which **are** chronological —
that is the Phase 7 fix #1. Different rule, different level.)

## Existing violations in AntCat

| | protonyms | share |
|---|---|---|
| with ≥2 distinct-type items | 13,430 | — |
| any out-of-order pair | 1,512 | 11.3% |
| **violating a strong rule** (≥90% dominance, excluding ambiguous types) | **243** | **1.8%** |

The strong-rule set is dominated by one pair — 204 of 243 are `Junior synonym of` placed before
`Subspecies of` (correct direction 93% of 3,074). The remaining 39 are scattered across 13 pairs,
each in single digits.

**Do not bulk-reorder on this basis.** 243 records is small enough to review, and the 204-record
cluster is concentrated enough to suggest either a systematic import artifact or a legitimate
exception — resolve that with Bradley before touching anything.

## Before this drives a writer

This was derived from the rendered dump, which per §0.1 is an index, not a source. The dump
preserves position order faithfully so the shape is trustworthy, but confirm against the real
column before `insert_at` depends on it (Appendix A, `history_order_export.rb`).

---

# 3. Landmines

## 3.1 Author normalisation returns ZERO matches (silent)

`protonym.py`'s `authorkey()` assumes a **bare surname** on both sides. This holds inside
`diff_history.py` because that parses AntCat's *history HTML*, whose first line yields a bare
surname.

It does **not** hold for database exports. `Reference#author_names_string` gives
`"Smith, M. R."` and `"Galvis, J. P.; Fernández, F."`. Feed those to `protokey()` and you get
**zero matches with no error** — the failure is total and silent.

The symmetric normalisation (verified to give 99.2% on 2026 data):

```python
def surname_first(a):
    """First author, surname portion, FIRST word.
       AntCat 'Baroni Urbani, C.' -> baroni ; NGC 'Baroni' -> baroni"""
    a = (a or '').split(';')[0]     # first author only
    a = a.split(',')[0]             # drop initials
    a = fold(a).strip()             # strip accents
    toks = [t for t in re.split(r'\s+', a) if t]
    return re.sub(r'[^a-z]', '', toks[0].lower()) if toks else ''
```

This belongs in the shared layer with the assumption documented at the call site.

## 3.2 Suffix letters are assigned independently

Bolton's `1972a` may be AntCat's `1972b` for the same paper. **Match on paper identity** (title +
page-in-pagination-range), never on the letter. Confirmed in 2026 for Kempf 1972 = `{ref 126357}`.

## 3.3 `X, in Y` vs `et al.`

Bolton writes `Smith, in Jones et al.`; AntCat writes `Jones et al.` Systematic false-positive
source. `_canon_in()` normalises it — **make sure it lives in the shared resolver**, not in one
pipeline.

## 3.4 Compound surnames

`Dalla Torre`, `Baroni Urbani`, `de Andrade`. Handle symmetrically — first word of the surname
portion on both sides. Asymmetric handling produces silent misses, not errors.

## 3.5 AntCat's history prose is not semicolon-delimited

Nearest-surname-before-year is the correct citation-keying model. First-author-per-segment was tried
and reverted.

## 3.6 Wrong data is worse than missing data

In a taxonomic catalogue a wrong reference id on a new line, or a wrong depository, is worse than an
absent citation. Verify every id on manual rows. Never auto-overwrite populated AntCat fields —
route conflicts to review.

## 3.7 Operational

- **Stale outputs**: always sync from `/tmp/work` to the outputs directory before presenting files.
- **`~/Downloads` is Dropbox** and rejects writes. Use `/tmp/` or `~/Desktop`.
- **Paperclip cross-device link log lines** are harmless INFO noise.
- Python scripts go in files and run under an interpreter; do not paste into zsh.
- Rails runners: `docker exec -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/<script>`

---

# 4. Migration plan

**Do not rewrite.** The existing pipelines are validated against real review rounds; a
half-migrated refactor is worse than the current scattered state, and there is one maintainer.

1. **Extract without behaviour change.** Move `citation_match.py`, the depository resolver, and
   `surname_first()` into a shared `resolve/` package. Change no logic.
2. **Prove parity.** Re-run the 2026 history diff through the shared layer. It must reproduce the
   same review sheets, row for row. This is the regression test — keep the 2026 outputs as fixtures.
3. **Migrate one pipeline.** Status-as-species first (smallest, best understood). Verify.
4. **Then the next.** History acts, then type material.
5. **Only then** restructure `parse_bolton.py` to emit structured fields, and migrate consumers off
   `block_text` one at a time.

Do the extraction while waiting on Bradley — it is not blocked by his review. Do the migration
after his round lands, so code and data are not moving simultaneously.

---

# 5. Regression metrics

Record these every run in `antcat_open_items.md`. Once AntCat absorbs a round of corrections, the
residuals should **shrink**. If they do not, either the corrections did not land or the diff is
wrong — and this is the only way you will notice.

| metric | 2026 baseline |
|---|---|
| NGC species-group headwords parsed | 23,718 |
| AntCat species-group protonyms | 24,330 |
| protonym key match rate | 99.2% (22,298 / 22,468) |
| depository concordance (raw) | 94.0% |
| depository concordance (after resolution) | 95.9% |
| depository residual | 740 |
| — NGC has extra (actionable) | 187 |
| — both differ | 139 |
| — AntCat has extra (likely AntCat correct) | 414 |
| type-material fill candidates | 11 |
| Barry errata raised (depositories) | 21 |
| AntCat institution gaps | 1 (`PMCT`) |
| history-order consistency (pairwise) | 94.1% of 32,445 |
| protonyms violating a strong order rule | 243 (1.8% of 13,430) |

---

# Appendix A — AntCat query cookbook

All read-only. Write to `/var/www/antcat-2/tmp/` (host) = `/app/tmp/` (container). Run with:

```bash
docker exec -w /app -e RAILS_ENV=production antcat-app \
  bundle exec rails runner tmp/<script>.rb
```

**Always print counts.** A runner that silently writes zero rows is the most expensive failure mode
here — the `rescue` inside a `find_each` loop will swallow a wrong method name on every row and
still exit 0.

### Existing runners

| script | emits |
|---|---|
| `export_protonyms.rb` | one JSON per species-group protonym: id, name, author, year, fossil, locality, bioregion, and the three type taxt fields |
| `export_references.rb` | reference table with nested containers resolved |
| `institutions_export.rb` | `institutions` table verbatim (id, abbreviation, name, grscicoll_identifier) |
| `type_recon.rb` | read-only field check + coverage counts + raw taxt samples |
| `history_order_export.rb` | **to write** — confirms §2A against real `position`, not the rendered dump |

### `history_order_export.rb` (to write)

Confirms the derived type order against the actual column before any `insert_at` depends on it:

```ruby
# history_order_export.rb -- READ ONLY.
require 'json'
OUT = Rails.root.join('tmp', 'history_order.jsonl')
n = 0
File.open(OUT, 'w') do |f|
  Protonym.find_each(batch_size: 500) do |p|
    items = p.history_items.order(:position).map { |i| { pos: i.position, type: i.type,
                                                         head: i.taxt.to_s[0, 60] } }
    next if items.size < 2
    f.puts({ protonym_id: p.id, items: items }.to_json)
    n += 1
  end
end
puts "wrote #{n} protonyms with >=2 history items to #{OUT}"
```

Note production stores most history as freeform `Taxt`, so `i.type` will often be `'Taxt'` and the
type label has to come from the taxt prefix — same normalisation as §2A. That is expected, not a
problem; it is why the dump-based derivation was valid in the first place.

### Writing a new one

The pattern that has worked:

```ruby
# <name>.rb -- READ ONLY. No writes.
require 'json'
OUT = Rails.root.join('tmp', '<name>.jsonl')
scope = <Model>.where(...)
puts "to export: #{scope.count}"                     # print BEFORE
n = 0
File.open(OUT, 'w') do |f|
  scope.find_each(batch_size: 500) do |r|
    f.puts({ id: r.id, ... }.to_json)
    n += 1
  end
end
puts "wrote #{n} rows to #{OUT}"                     # print AFTER
```

**Verify field names before a long export.** A 10-second probe beats a 5-minute run that returns
nothing:

```ruby
puts <Model>.column_names.inspect
puts <Model>.new.respond_to?(:<field>)
```

### Useful facts

- `Reference`'s author column is **`author_names_string_cache`**, not `author_names_string`.
- `Institution#name` carries alias information as an `[Also X; Y]` or `[Formerly X]` prefix.
  Union-find over that graph gave 610 equivalence classes from 784 rows (138 multi-code).
- `Protonym` type columns: `primary_type_information_taxt`, `secondary_type_information_taxt`,
  `type_notes_taxt` (plus `type_name_id`, `gender_agreement_type`).
- Species-group name types: `SpeciesName`, `SubspeciesName`, `InfrasubspeciesName`.
- AntCatBot is user id 62 — re-confirm each run: `User.where(name: 'AntCatBot').pluck(:id)`

---

# Appendix B — Time budget

| phase | cost |
|---|---|
| 0 inputs + `.doc` conversion | minutes |
| 1 NGC parse | minutes |
| 2 AntCat extraction | minutes per runner, plus transfer |
| 3 entity resolution | minutes once built |
| 4 entity review [gate 1] | Bradley/Barry turnaround, async |
| 5 content comparison | minutes |
| 6 content review [gate 2] | Bradley turnaround, async |
| 7 the write | an afternoon |
| 8 record & close | under an hour |

The first run of anything is slow because the data model is being discovered. That work is done and
captured — a repeat run should not re-investigate. If a session starts turning into investigation,
stop and check whether `LIVE_CONSOLE_FINDINGS.md` already answers it.

# AntCat comparison pipelines — master reference

Maintainer: Brian Fisher. Cadence: run the full comparison against a fresh AntCat dump
roughly every 6 months (Bolton issues catalogue updates; AntCat curation moves continuously).

This document is the single reference for the three comparison/export pipelines that keep
AntCat synchronized with Barry Bolton's catalogue and feed the TaxonWorks migration. It
covers what each does, how to run it, the inputs it needs, the results as of the last run,
and the hard-won lessons that shaped the code. Keep it beside the scripts.

---

## The three workstreams

| # | Workstream | Purpose | Maturity |
|---|-----------|---------|----------|
| 1 | **Bolton NGC ↔ AntCat history diff** | Yearly diff of Bolton's catalogue against AntCat at the taxonomic-act / history level. Surfaces acts and citations AntCat is missing, and errors in Bolton's catalogue. | Mature |
| 2 | **AntCat → TaxonWorks export** | Export AntCat names + references in TaxonWorks-compatible TSV + BibTeX. | Mature |
| 3 | **Status-as-species reference diff** | Find citations Bolton has on "Status as species" (and other faunistic) history lines that AntCat is missing; resolve each to an AntCat reference id and emit ready-to-insert markup. | Refined; write-to-AntCat step pending |

All three share three core modules (in `shared/`): `diff_history.py` (the AntCat loader +
citation parser), `protonym.py` (protonym-identity pairing), `parse_antcat.py` (dump parser).

---

## Shared foundations (read this first)

### Protonym identity is the cross-catalogue key
A name is matched between catalogues by its **protonym identity** = (original genus, original
terminal epithet, 4-digit year) — NEVER by current spelling. ~6.4% of names have a published
spelling that differs from the current gender-agreed spelling; matching on current spelling
silently loses them.

### AntCat history is editable "taxt" markup
AntCat stores each name's taxonomic history as editable markup with citations written
`{ref NNNNN}: page` (rendered online as a linked `[Author, year](/references/NNNNN): page`).
This is why adding a citation is inserting one token, not prose surgery. AntCat calls this
markup format **"taxt"** — the term to grep for in the Rails codebase.

### The two catalogues have different prose shapes
- **AntCat history**: one long run, NOT semicolon-delimited; the first surname in the run is
  the genus author, not a citation. Citation keying uses nearest-surname-before-year.
- **Bolton**: semicolon-delimited, one citation per segment.
Any change to citation parsing MUST be tested on BOTH shapes — a fix for one silently breaks
the other. This has bitten the project repeatedly.

### Validate counts row-by-row, never trust an aggregate
Plausible-looking totals have been wrong ~7 times across this project. Every reported count
must be validated against AntCat's ACTUAL data (both status field AND history text — they can
disagree; Bradley Reynolds adjudicates). Edit-distance / fuzzy matching SUGGESTS for a human;
it must never DECIDE identity.

---

## Workstream 1 — Bolton NGC ↔ AntCat history diff

**Scripts:** `shared/parse_antcat.py`, `bolton_diff/parse_bolton.py`, `shared/diff_history.py`
(main), `bolton_diff/diff_catalogue.py` (genus/species presence), `shared/protonym.py`,
`bolton_diff/export_references.rb` (runs on the droplet to dump references).

**Run:**
```
# 1. parse both catalogues
python3 shared/parse_antcat.py <worldants.txt> <outdir>
python3 bolton_diff/parse_bolton.py bolton_docx bolton_out

# 2. the history-level diff (the main output)
python3 shared/diff_history.py --bolton-dir bolton_out --worldants <worldants.txt> \
        --out-dir <outdir> [--recent-from 2015]

# 3. genus/species presence diff (needs parse_antcat output first)
python3 bolton_diff/diff_catalogue.py ...
```

**What it produces:** sheets of acts/citations AntCat is missing (the "added-refs" sheet),
recent-acts, unresolved targets, plus errata for Barry Bolton (his catalogue's own errors).
Bradley reviews these against original publications; his notes drive parser fixes.

**Bug classes fixed (all encoded in the code, don't reintroduce):** "X, in Y" author-vs-
publication citations (`_canon_in` rewrites to publication author); multi-author citations
keyed on the wrong author (emit keys under first author AND nearest surname, judge once
grouped by year); online-early vs formal year (suppress a same-author citation within 1 year
on the same name only); label-stripping before parsing (else "Status"/"species" parse as
surnames).

---

## Workstream 2 — AntCat → TaxonWorks export

**Scripts:** `taxonworks_export/export_antcat_names.py`, `export_antcat_bibtex.py`,
`export_references.rb` (runs on droplet), `build_tw_exports.sh` (one-command wrapper,
self-validating), `shared/protonym.py`.

**Run (one command):**
```
bash taxonworks_export/build_tw_exports.sh <worldants.txt> antcat_references.csv tw_out
```
Produces `antcat_names.tsv` (~23,090 names, protonym-keyed, homonym replacements resolved)
and `antcat_references.bib` (~12,979 entries, nested containers via crossref). Built-in
validation: strict BibTeX parse, crossref integrity, join-coverage checks.

**Key fix:** BibTeX brace-delimited values need BALANCED braces/brackets — the parser aborts
on an unbalanced brace. `bib_value()` balances via depth-tracking (don't escape, balance).

**Open unknown:** TaxonWorks API write capability for id-linking is unconfirmed. The export is
correct; the ingestion path into a live TW project has not been proven.

---

## Workstream 3 — Status-as-species reference diff (most recently refactored)

**Scripts:** `status_refs/diff_status_refs.py` (finds missing citations),
`status_refs/resolve_status_refs.py` (resolves to reference ids + tokens),
`status_refs/citation_match.py` (the matcher), plus `shared/diff_history.py`, `protonym.py`,
`parse_antcat.py`.

**Run:**
```
# 1. find missing citations on Status-as-species (and other faunistic) lines
python3 status_refs/diff_status_refs.py --bolton-dir bolton_out \
        --worldants <worldants.txt> --out-dir status_out
#   (add --only-status to restrict to "Status as species" lines)

# 2. resolve each to an AntCat reference id + ready-to-insert token
python3 status_refs/resolve_status_refs.py --status status_out/status_refs_to_check.csv \
        --refs antcat_references_v2.csv --bolton-refs bolton_out/bolton_references.csv \
        --out-dir status_out
```

**Why it exists:** AntCat is weakest at entering references on "Status as species" lines, and
`diff_history.py` deliberately skips them. This is the largest pool of potentially-missing
citations. `diff_status_refs.py` scans all 8 citation-bearing Bolton line types (Status as
species is ~90%): Status as species, As unavailable (infrasubspecific), Incertae sedis, Nomen
dubium/oblitum, Unidentifiable, Unplaced, Combination (provisional). It deliberately excludes
Current subspecies (name lists, no citations), Replacement name (handled by workstream 1), and
Type-material/Distribution (metadata).

**Outputs:**
- `status_refs_upload_ready.csv` — the worklist. Column `token` is ready `{ref N}: page
  (qualifier)` markup. Column `action` is one of:
  - `append` — add token to the existing Status line
  - `create_line` — species has no Status line; token is a whole new history item
  - `create_line_manual` — Bolton's line has extra pre-2015 citations; build by hand
- `status_refs_needs_pick.csv` — citations needing a manual reference-id pick
- `status_refs_by_paper.csv` — the missing citations grouped by source paper (the review unit)
- `status_refs_to_check.csv` — full audit trail (every citation + the full Bolton line)

### The matcher (`citation_match.py`) — the core of the 2026 refactor

The single function `citation_present(bolton_segment, antcat_text)` decides whether AntCat
already cites the paper Bolton names. It replaced a fragile stack of four interacting fuzzy
key-checks. It compares the **first author + year with signature confirmation**:

- **spelling variants match** — Bolton "Báthory 2024" == AntCat "Báthori 2024" (edit distance 1
  on names ≥6 chars); also Galkowsky/Galkowski, Pérez-Gonzáles/Pérez-González
- **compound / hyphenated surnames match** — "Hita Garcia" == "Hita-Garcia",
  "Casadei-Ferreira" (comma/&-groups joined; prefix rule guarded so short names like
  chen/chenzhang and smith/smithson do NOT merge)
- **surname particles match** — Bolton "Silva" == AntCat "Da Silva" (leading da/de/van/von/…
  stripped)
- **a redescription is NOT matched to a same-author original description** — Bolton
  "Xu, Liu, et al. 2024" (redescription) != AntCat "Qian & Xu, 2024" (original description),
  even though both share author "Xu" and year 2024. This was the subtle false-negative bug.
- **Unicode is normalized to NFC** — the dump stores some accents decomposed (e.g. "Guénard"
  as e + combining acute); without normalization the combining mark breaks the author match
  and the citation is wrongly reported missing. (This was the "Wong 2016a" failure.)

**Regex gotcha, do not undo:** year matching must allow the disambiguation letter
(`2020a`, not `2020\b` — the `\b` fails between a digit and a letter and caused ~1000 false
negatives).

---

## Results as of the last run (July 2026 dump: `20260716-05_04_57-worldants.txt`)

**Status-as-species reference diff (workstream 3):**
- **565 missing citations, 100% auto-resolved** to reference ids with complete tokens
- Actions: 502 append, 61 create_line, 2 create_line_manual
- 86 tokens carry a `(redescription)` / `(in key)` qualifier
- 0 rows need a manual reference pick (all resolved)
- 21 antcat_ids were hand-corrected by Bradley (misspelling-record targets) and are authoritative
- The missing citations cluster on 14 papers: Khalili-Moghadam 2026 (287 species), Dong 2025
  (87), Xu 2024 (82), Hamer 2025 (66), Lebas 2025 (24), and 9 smaller.

**Why the count rose across review rounds** (496 → 565): the earlier matcher was
*under-reporting*. Each fix (the redescription/description collision, then the NFC accent bug)
recovered genuine missing citations that were being wrongly suppressed. A rising count meant
the tool getting more correct, not less — it should stabilize now that matching is sound.

**Errata sent to Barry Bolton** (his catalogue's own errors, separate from AntCat gaps): two
batches. First batch (spelling/target typos) already corrected by Barry. Round 7 (4 items):
Strumigenys incerta (synonymy not in cited source), Dorylus perseus and Solenopsis saudiensis
(stale synonymies no longer valid), Seifert misspelled "Siefert" ×4. Note: Báthori is NOT an
erratum — Bradley confirmed that is the correct spelling.

---

## The write-to-AntCat step (workstream 3 — NOT yet built)

Turning the 563 script-writable tokens into actual AntCat edits is a separate, careful task.
Before writing anything, three data-model questions must be answered by inspecting the live
Rails app (models likely `taxon_history_item.rb`, `protonym.rb`, a taxt parser/renderer;
search the repo for `taxt`):
1. Is a "Status as species" line independently addressable, or is the history one blob per name?
2. How is edit provenance recorded (for a reversible, attributable bulk write)?
3. Is the `{ref N}: page` markup validated/parsed on save, preserving rendering and order?

Write discipline (non-negotiable): DigitalOcean snapshot → dry-run (log only) → single canary
write verified in the live UI → ~10-row batch verified → full 563. Everything reversible.

---

## Standard environment & conventions

- **Working data dir:** a scratch dir (e.g. `/tmp/w/`). Re-extract inputs if gone.
- **Dump filename gotcha:** the dump zip is named with a DOT (`...worldants.txt.zip`), so a
  `*-worldants_txt.zip` wildcard fails in zsh — unzip by exact name.
- **worldants.txt parsing:** `csv.field_size_limit(sys.maxsize)`, `errors='replace'`. Column
  17 (taxonomic history) — first line is the protonym as published (the original description).
  Reference id column is 100% populated.
- **Droplet runner pattern:**
  `docker exec -w /app -e RAILS_ENV=production antcat-app bundle exec rails runner tmp/<script>`
- **Output paths:** write to `/tmp/` — Brian's `~/Downloads` is a Dropbox CloudStorage path
  that rejects writes.
- **Python scripts** are saved as files and run with the interpreter (not pasted into zsh).
- Only pip dependency for the pipelines: **python-docx** (for parse_bolton); bibtexparser
  optional for strict BibTeX validation.

---

## Inputs each run needs

- **Bolton catalogue** — the `AA_CATALOGUE_2026.zip` (594 .docx). Extract:
  `unzip -j -o -q AA_CATALOGUE_2026.zip "*.docx" -d bolton_docx`
- **Fresh AntCat dump** — `NNNNNNNN-...-worldants.txt` (~32,900 name rows)
- **AntCat references CSV** — `antcat_references_v2.csv` (~12,979 refs, with nested container
  columns) — produced by `export_references.rb` on the droplet

---

## Reviewer workflow (Bradley Reynolds)

Bradley verifies every reported gap against the original publication. His annotation rounds are
the primary driver of parser refinements — the tool proposes, he adjudicates. His spot-checks
have caught bugs in BOTH directions (over-reporting false positives from spelling/encoding, and
under-reporting from author+year key collisions). Send him the paper-level summary first
(`status_refs_by_paper.csv`), not the row-level detail — paper-level is the real review unit.

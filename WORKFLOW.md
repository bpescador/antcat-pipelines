# AntCat → TaxonWorks sync — WORKFLOW

The shared runbook for the **AntCat** and **TaxonWorks** Claude projects. Code
lives in this repo; "current" = `main`. Session-start line for either project:
*"AntCat↔TW sync: canonical code and runbook at
github.com/bpescador/antcat-tw-sync. Fetch WORKFLOW.md and the files it
references before acting; WORKFLOW.md is the process."*

Deep TW-side detail (import mechanics, failure modes, evidence): see
`antcat_dwca_checklist_import.md` in this repo.

Every command block states WHERE it runs. One machine per block, always.

## Standing rules (never skip)

- **Names match on protonym identity** — (original genus, terminal epithet,
  first-author surname, 4-digit year) — never on current spelling. AntCat
  gender-agrees epithets; ~6.4% differ from the published spelling.
- **AntCat is authoritative for names; the PDF is authoritative over AntCat.**
  When data conflict: PDF > AntCat > TW production > a stale sandbox.
- **Read-only first, sandbox before production, no deletions.** The TW BibTeX
  loader does NOT dedup and there is NO bulk Source delete — a bad load is
  recovered only by project reset. Load references exactly once.
- **Obsolete-combination rows are not names** — they are TW Combination
  objects. Never import them as TaxonNames.
- **Same-moment rule:** the worldants dump and the reference CSV must come
  from the same AntCat moment (dump same day as, or earlier than, the CSV) —
  or names will cite references the .bib lacks.
- **Tokens** live in env vars (`TAXONWORKS_API`, `TAXONWORKS_TOKEN`,
  `TAXONWORKS_PROJECT_TOKEN`), never inline. Never in git, never in chat.

## The three files TaxonWorks needs

| File | What it is | Built by |
|---|---|---|
| `antcat_references.bib` | AntCat references as BibTeX; AntCat id on the key (`antcatNNNN`); nested chapters `crossref` to their container | `export_antcat_bibtex.py` |
| `antcat_names.tsv` | one row per name (protonym identity); carries `reference_id` + `reference_pages` | `export_antcat_names.py` |
| `origin_citation_links.tsv` | `taxon_name_id, source_id, pages, antcat_reference_id, protonym_key` | `build_origin_citation_links.py` |

## Stage 1 — AntCat export (the only step touching AntCat production; read-only)

```bash
# WHERE: droplet (ssh antcat)
curl -sO https://raw.githubusercontent.com/bpescador/antcat-tw-sync/main/export_references.rb
docker cp export_references.rb antcat-app:/app/
docker exec -w /app -e RAILS_ENV=production antcat-app \
    bundle exec rails runner /app/export_references.rb
# expect: "Wrote NNNNN references"; nested-with-container should be ~1,245, never ~0
```

```bash
# WHERE: Mac Terminal
scp antcat:/var/www/antcat-2/antcat_references.csv ~/antcat/taxonworks_sync/
```

The worldants dump comes from the daily 05:04 auto-export.

## Stage 2 — build names + BibTeX

```bash
# WHERE: any machine with python3 and this repo
./build_tw_exports.sh <worldants.txt> <antcat_references.csv> tw_out
```

Gates, all mandatory: `RESULT: PASS` (strict BibTeX parse, zero unbalanced
braces, crossref closure) and `join check ... 100.00%`. Anything less: stop,
diagnose, regenerate. Never hand-patch the outputs.

## Stage 3 — build the link file

Requires the names to exist in the target TW instance first. TW inputs come
from Filter Nomenclature (names) and Filter Sources (references), each split
into parts by the silent 10,000-row export clamp — pass comma-separated. The
Source CSV export drops Identifiers; the script recovers the AntCat id from
the `[antcat_id: N]` note in the `cached` string.

```bash
# WHERE: any machine with python3 and this repo
python3 build_origin_citation_links.py \
    --antcat-names tw_out/antcat_names.tsv \
    --tw-taxa taxon1.csv,taxon2.csv,taxon3.csv \
    --tw-sources ref1.csv,ref2.csv \
    --out origin_citation_links.tsv
```

Gates: 0 duplicate `taxon_name_id`s; compare against the previous validated
links file on shared ids — reference and pages agreement ~100%, and **every**
disagreement inspected row-by-row against the dump text before acceptance
(this is how 5 surviving page artifacts were caught in Aug 2026).

## Stage 4 — load references as Sources in TW

The checklist importer consumes no citation field, so references load
separately, first.

- **Server-side (production and any large load):** `Source.batch_create`.
  Store the BibTeX label (`antcatNNNN`) as an
  `Identifier::Local::Import::Bibtex` in the `antcat_ref` namespace.
- **UI (small/sandbox only):** Sources → Batch load → BibTeX. Preview scales;
  **Create 504s at ~2,000 but the write succeeds** — verify by Source count,
  never retry a counted chunk, chunk to ~2,000 with crossref clusters intact.
- **Verify:** Source count matches; `antcatNNNN` queryable via Source Filter →
  Identifiers facet + `antcat_ref` (NOT keyword/note search).

## Stage 5 — create the origin citations

**No API write path exists** (citation endpoints are read-only): server-side.
`source_id` in the file is instance-specific — re-resolve on the target:

```ruby
# 1. antcat_id -> target source_id, from the Identifiers created in Stage 4
# 2. for each row of origin_citation_links.tsv:
Citation.create!(
  citation_object: TaxonName.find(taxon_name_id),
  source_id: <resolved via antcat_reference_id>,   # NOT the file's source_id
  pages: pages,
  is_original: true
)
```

`taxon_name_id` values are valid on the target instance directly.

## Stage 6 — verify, then production

Sandbox first. Inspect a sample of applied citations in the UI (origin
citation shows, page correct, verbatim retained). Then repeat Stages 1–5
against production on a same-day AntCat export.

## Known gotchas (detail in `antcat_dwca_checklist_import.md`)

- **Author mismatches are usually nested-chapter attribution, not errors.**
  AntCat records a name at its chapter authorship (a subset of the container's
  authors); the shorter list is correct. Check the PDF heading before "fixing".
- **Pages:** post-fix, a `pages == 10` is genuine (76 of 81 confirmed in Aug
  2026; the 5 artifacts were corrected to blank). Roman-numeral pages (`civ`)
  and unpaginated supplements are blank by design — AntCat prose has the
  values.
- **Keep TW verbatim author/year** — don't delete on agreement.
- **Origin-citation `pages` (name's description page) ≠ Source `pages`
  (whole-work range).** Different fields; don't conflate.
- **`Failed` dataset records** hide their exception and can't be retried —
  diagnose on a local instance, not from the workbench.
- `build_origin_citation_links.py` is a reconstruction (original inline code
  lost). Measured 2026-08: 20,100/20,781 recall (96.5%), 100.00% accuracy on
  shared rows. The Tom-validated TSV was canonical for the 2026-08 cycle; the
  script is the method for the next.

## Getting fixes into TaxonWorks

Merged PRs, not meetings, are how work lands; the differentiator is
**demonstrated testing**. First code target: #4987 (typeStatus import bug).
See the runbook's contribution-strategy section.

## Data conventions

Repo = code and docs only (`.gitignore` enforces it). Data lives in
`~/antcat/taxonworks_sync/` with dated, immutable zip snapshots in
`~/antcat/snapshots/` (each with `CHANGELOG.md` + `MANIFEST.sha256`; verify:
`shasum -a 256 -c MANIFEST.sha256`). Snapshots copy to Google Drive offsite.

## History

- **2026-08-15** — TW-project payload reconciled into the repo; workflow docs
  merged into this single file; TW import runbook added.
- **2026-08-14** — production set built and verified in an AntCat-project
  session: 12,994 references / 23,100 names / 20,781 triples; join 100.00%;
  BibTeX PASS; 5 page artifacts corrected; 4 new refs included as Sources.
- **2026-07-11/21** — pipeline built across TaxonWorks-project sessions;
  sandwich load validated by Tom.

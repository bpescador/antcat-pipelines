# AntCat → TaxonWorks sync — WORKFLOW

This is the shared runbook for the **AntCat** and **TaxonWorks** Claude projects.
Code lives in this repo; "current" = `main`. Session-start line for either
project: *"Code is at github.com/bpescador/antcat-pipelines — clone main;
WORKFLOW.md is the runbook."*

Every command block states WHERE it runs. One machine per block, always.

## Stage 1 — reference CSV + dump (the only step touching AntCat production; read-only)

```bash
# WHERE: droplet (ssh antcat)
curl -sO https://raw.githubusercontent.com/bpescador/antcat-pipelines/main/export_references.rb
docker cp export_references.rb antcat-app:/app/
docker exec -w /app -e RAILS_ENV=production antcat-app \
    bundle exec rails runner /app/export_references.rb
# expect: "Wrote NNNNN references"; nested-with-container should be ~1,245, never ~0
```

```bash
# WHERE: Mac Terminal
scp antcat:/var/www/antcat-2/antcat_references.csv ~/antcat/taxonworks_sync/
```

### Where the worldants dump comes from

It is **not** produced on antcat-prod, and not by the 05:04 job. It is
generated nightly ~03:00 PT on a separate bridge box,
`antcat-export.antweb.org`, by `/root/antcat/docker/export_database.sh`: that
script pulls a fresh mysqldump from antcat-prod over the private network,
loads it into a throwaway dockerized AntCat, and runs `rake antweb:export`,
writing `/root/antcat/database_export/antcat.antweb.txt` (~140 MB). AntWeb
fetches that file at 05:04 PT and renames it
`YYYYMMDD-HH_MM_SS-worldants.txt` — same file, AntWeb's name. Either name is
the same content.

```bash
# WHERE: Mac Terminal
scp antcat-export:/root/antcat/database_export/antcat.antweb.txt worldants.txt
```

The `antcat-export` alias is in Brian's `~/.ssh/config`; port 9090 on that box
is firewalled externally. No IP addresses belong in this file.

**Same-moment rule:** the dump must be from the same day as (or earlier than)
the CSV — never newer, or names will cite references the .bib lacks. Because
the dump reflects prod as of ~03:00 PT, a reference CSV exported later the
same day always satisfies the rule. The trap is the reverse: a CSV left over
from a previous cycle is *older* than today's dump and must not be reused —
re-run the Stage 1 export instead.

## Stage 2 — names + BibTeX (Mac, droplet host, or a Claude session)

```bash
# WHERE: any machine with python3 and this repo
./build_tw_exports.sh <worldants.txt> <antcat_references.csv> tw_out
```

Gates, all mandatory: `RESULT: PASS` (strict BibTeX parse, zero unbalanced
braces, crossref closure) and `join check ... 100.00%`. Anything less: stop,
diagnose, regenerate. Never hand-patch the outputs.

## Stage 3 — origin-citation links

TW-side inputs (exported from the target TW instance): Filter Nomenclature
CSV part(s) and Filter Sources CSV part(s) — the 10k export clamp forces
multiple files; pass them comma-separated. Note: the Source CSV export drops
Identifiers; the AntCat id is recovered from the `[antcat_id: N]` note in
`cached` (documented in the script header).

```bash
# WHERE: any machine with python3 and this repo
python3 build_origin_citation_links.py \
    --antcat-names tw_out/antcat_names.tsv \
    --tw-taxa taxon1.csv,taxon2.csv,taxon3.csv \
    --tw-sources ref1.csv,ref2.csv \
    --out origin_citation_links.tsv
```

Gates: 0 duplicate `taxon_name_id`s; compare against the previous validated
links file on shared ids — reference and pages agreement should be ~100%, and
**every** disagreement gets inspected row-by-row against the dump text before
acceptance (this is how 5 surviving page artifacts were caught in Aug 2026).

## Handoff

Three files to Tom: `antcat_references.bib`, `antcat_names.tsv`,
`origin_citation_links.tsv`. The `source_id` column is instance-specific;
Tom re-resolves it on the target instance via `antcat_reference_id` (stable).

## Known caveats — 2026-08 cycle

- `build_origin_citation_links.py` is a reconstruction of logic originally
  built inline (source lost). Measured this cycle: 20,100/20,781 recall
  (96.5%), **100.00% accuracy** on shared rows. The Tom-validated TSV is
  canonical for this cycle; the script is the method for the next.
- Roman-numeral pages (`civ`) and unpaginated supplements are **blank by
  design** — 5 such rows; AntCat prose carries the values.
- The 4 new 2026 references (144722/144727/144729/144732) load as Sources but
  have no citation rows until their names exist in TW.
- PAGE_RE history: pre-Aug-2026 exports leaked DOI prefixes (`10`) into pages.
  Fixed at source in `export_antcat_names.py`; do not reuse pre-fix TSVs.

## Data conventions

Repo = code and docs only (`.gitignore` enforces it). Data lives in
`~/antcat/taxonworks_sync/` with dated, immutable zip snapshots in
`~/antcat/snapshots/` (each with `CHANGELOG.md` + `MANIFEST.sha256`;
verify: `shasum -a 256 -c MANIFEST.sha256`). Snapshot zips are copied to
Google Drive for offsite.

## History

- **2026-08-14** — production set built and verified in an AntCat-project
  session: 12,994 references / 23,100 names / 20,781 triples; join 100.00%;
  BibTeX PASS; 5 page artifacts corrected; 4 new refs included as Sources.
- **2026-07-11/21** — pipeline built across TaxonWorks-project sessions;
  sandwich load validated by Tom.

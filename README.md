# antcat-tw-sync

The AntCat → TaxonWorks name-and-reference sync pipeline.

**This repo is the single source of truth for the code.** "Current" means: what
is on `main`. Zips are for **data** snapshots only (dumps, CSVs, outputs) —
code is never distributed by zip again.

## The pipeline — two stages, two machines

```
STAGE 1 — AntCat droplet (the only step that touches production; read-only)
  export_references.rb  (rails runner)  → antcat_references.csv
  worldants dump                        → worldants.txt
        │  copy both to the machine running stage 2
        ▼
STAGE 2 — anywhere with python3 (Mac, droplet host, or a Claude session)
  build_tw_exports.sh <worldants.txt> <antcat_references.csv> tw_out
        → tw_out/antcat_names.tsv        (export_antcat_names.py + protonym.py)
        → tw_out/antcat_references.bib   (export_antcat_bibtex.py)
        + self-validates: strict BibTeX parse, crossref closure, join check
        ▼
STAGE 3 — citation links
  build_origin_citation_links.py (TODO: not yet in repo — see below)
        → origin_citation_links.tsv
        ▼
HANDOFF — three files to Tom (TaxonWorks): .bib, names .tsv, links .tsv
```

Stage 1 commands (droplet):

```bash
ssh antcat
docker cp export_references.rb antcat-app:/app/
docker exec -w /app -e RAILS_ENV=production antcat-app \
    bundle exec rails runner /app/export_references.rb
# output lands on host at /var/www/antcat-2/antcat_references.csv
```

Stage 2 command:

```bash
./build_tw_exports.sh worldants.txt antcat_references.csv tw_out
# prints PASS/FAIL; PASS means the files are load-ready
```

## Rule: both inputs from the same export

The names file and the .bib must come from the **same moment** of AntCat, or
names will cite references the .bib lacks (this happened: a Jul-11 .bib vs an
Aug dump left 4 brand-new 2026 references unlinkable). Always regenerate the
CSV and the dump together, then run stage 2 on that pair.

## Incomplete — two files still to add (as of 2026-08-14)

1. **`protonym.py`** — imported by `export_antcat_names.py`
   (`parse_protonym`, `strip_html`, `fold`, `year4`, `authorkey`). Lives on
   Brian's Mac in the folder with `build_tw_exports.sh`, and in the TaxonWorks
   Claude project. Commit it here; the pipeline cannot run without it.
2. **`build_origin_citation_links.py`** — the stage-3 join script, currently
   only inside a TaxonWorks-project chat. Export it from that chat and commit.

## Running it "on its own" (Claude sessions)

Any Claude session (AntCat or TaxonWorks project) can run stage 2/3:
clone this repo (github.com is reachable from the session sandbox), then
upload only the two data files to the chat. No more guessing which script
copy is current — the session fetches `main`.

## Data-snapshot convention (unchanged)

Working data folders live in `~/antcat/`; every data handoff is a dated zip
in `~/antcat/snapshots/` with a `CHANGELOG.md` and `MANIFEST.sha256`
(`shasum -a 256 -c MANIFEST.sha256` verifies). Snapshots are never edited or
overwritten. Snapshot zips also get copied to Google Drive for offsite.

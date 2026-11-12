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
# -u antcat: since AntCat #1578 the app runs as user antcat; a runner started as the container default (root) can leave root-owned files the app cannot write (checked on antcat-staging 2026-11-03).
# If it cannot write /app/antcat_references.csv, that is the open item to move this output to tmp/.
docker exec -u antcat -w /app -e RAILS_ENV=production antcat-app \
    bundle exec rails runner /app/export_references.rb
# expect: "Wrote NNNNN references ... (csv 3.x)"; nested-with-container should be ~1,245, never ~0
# A warning "csv used to be loaded from the standard library ... since Ruby 3.4.0" comes first:
# harmless (Bundler, before the script loads Ruby's own csv). Tested on antcat-prod 2026-11-11:
# 13,043 references, 1,248 nested, csv 3.3.5.
# Before copying: the CSV's date must be today. A failed export leaves the previous
# cycle's file in place, and the scp below would copy stale data without complaint.
date; ls -l --time-style=long-iso /var/www/antcat-2/antcat_references.csv
```

Ruby 4.0 (AntCat since Oct 2026): `csv` is no longer a default gem and is not in AntCat's
Gemfile. `export_references.rb` puts Ruby's own copy on the load path itself (2026-11-11), so
the command above needs no workaround. It writes to `/app/tmp/antcat_references.csv.tmp` first
and copies it over the CSV only when the export has finished.

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

**Prerequisite:** the strict-parse gate imports `bibtexparser` and uses its v1
API (`bibtexparser.loads`), so install v1 — `pip install 'bibtexparser<2'`
(v2 is a beta with a different API and will not work). Fresh machines and
agent sandboxes generally do not have it; a `ModuleNotFoundError` here is a
missing prerequisite, not a pipeline failure.

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

Three files: `antcat_references.bib`, `antcat_names.tsv`, `origin_citation_links.tsv`.
Since 2026-11-11 the TaxonWorks project loads them into TW production itself, through
Brian's logged-in Chrome session (project AntWeb on sfg.taxonworks.org); SFG (Tom) no
longer does the load. The `source_id` column is instance-specific; it is re-resolved on
the target instance via `antcat_reference_id` (stable; in TW the Source identifier is
namespace `antcat_ref`, value `antcatNNNN`).

## Stage 4 — status recount (after a TW load)

The TW project exports one row per TW Protonym (`tw_production_protonyms_YYYY-MM-DD.tsv`).
`tw_status_diff.py` joins it to `antcat_names.tsv` and lists the names whose status or
target differs:

```bash
python3 tw_status_diff.py --antcat tw_out_YYYYMMDD/antcat_names.tsv \
  --tw tw_production_protonyms_YYYY-MM-DD.tsv --out tw_status_YYYYMMDD
```

Outputs `tw_status_differences.tsv`, `antcat_not_matched.tsv` and `summary.txt`. The join
and the status rules are in the script's docstring. Differences in spelling or subgenus
alone do not count. Read the summary's "matched" line first: AntCat names not matched
should be a handful, each explained.

## Known caveats — 2026-08 cycle

- `build_origin_citation_links.py` is a reconstruction of logic originally
  built inline (source lost). Measured this cycle: 20,100/20,781 recall
  (96.5%), **100.00% accuracy** on shared rows. The Tom-validated TSV is
  canonical for this cycle; the script is the method for the next.
- Roman-numeral pages (`civ`) and unpaginated supplements are **blank by
  design** — 5 such rows; AntCat prose carries the values.
  **2026-11-11:** `original_page()` now reads only the protonym's own citation (the first
  year in the history text) and returns blank unless the token after its colon is an
  arabic number. Before, when that token was roman, a plate ("pl. 19") or missing, it took
  the first year-colon-number later in the first 200 characters, usually a lectotype
  designation: 21 wrong pages in the 11 Nov dump (Myrmica reticulata got "5" from
  "Seifert, 2026b ... : 5"; "260" in August). On the 11 Nov dump 174 names have a blank
  page: 78 roman, 7 plate only, 12 other non-numbers ("no. 1651", "named in fig. 1",
  "in supplementary"), 77 with no colon straight after the year. The 77 are protonyms
  whose DOI is written as a link ("https://doi.org/10...", "doi: 10...") before the colon.
  **Recovered the same day** (agreed by Brian and the TaxonWorks project: it only fills
  blanks): the parser now steps over DOI links too, and 76 get their page
  (`page_changes_doiurl_20261111.tsv`). The one left, Myrmoteras yamanei, has a space inside
  its DOI in AntCat ("10.15298/ invertzool..."), to fix in AntCat. Blank pages on the
  11 Nov dump after both fixes: 98.
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

- **2026-11-11** — 13,043 references / 23,142 names; join 100.00%; BibTeX PASS;
  49 new references and 42 new names since 2026-08-14. Two fixes found in this cycle:
  `export_references.rb` failed under Ruby 4.0 (`csv` LoadError; run once with a load-path
  workaround, now in the script) and `original_page()` took pages from later citations
  (21 names now blank, listed in `page_changes_20261111.tsv`); and DOI links before the
  page hid 76 real pages (now read; `page_changes_doiurl_20261111.tsv`). Build the handoff
  `antcat_names.tsv` with the fixed code: reference_pages parsed 23,044.
  **Production load complete the same day, done from the TaxonWorks project** (Brian's
  Chrome session, project AntWeb on sfg.taxonworks.org), not by SFG; Tom Klein's pending
  load is no longer needed. As reported by the TW project, each record read back: 13,043
  Sources (`antcat_ref`); origin citations 20,740 by protonym key plus 576 by current
  name, author and year; 356 Protonyms created plus 6 fossil genera and tribe
  Eridanomyrmini; 29 same-protonym placement updates; Lieberman et al. 2026 (17 names);
  the 131 type-status corrections. Per-record logs for the first four were lost when the
  browser tab reloaded; the TW Protonym export lists every name with its TW id.
  Recount (Stage 4, retires July's 1,953): 23,135 of 23,142 names matched; 122 status or
  target differences, 36 TW records missing a relationship, and 205 unidentifiable names that
  TW holds as valid with UncertainPlacement (a vocabulary question). It found a fault in `export_antcat_names.py`: a homonym
  could take the replacement name of a same-epithet homonym in another genus (2 rows in the
  11 Nov file; fixed in 7f6453e).

- **2026-08-14** — production set built and verified in an AntCat-project
  session: 12,994 references / 23,100 names / 20,781 triples; join 100.00%;
  BibTeX PASS; 5 page artifacts corrected; 4 new refs included as Sources.
- **2026-07-11/21** — pipeline built across TaxonWorks-project sessions;
  sandwich load validated by Tom.

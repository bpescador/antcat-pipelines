# Bolton catalogue ⇄ AntCat — yearly diff

Finds what Barry Bolton's hand-maintained catalogue contains that AntCat is
missing, across the three categories you review by hand: **references**,
**species-group names**, **genus-group names**. Distribution data is ignored.

The output is a small, classified worklist for **manual** entry into AntCat —
not an automated importer.

---

## What you need each year

1. **Bolton's catalogue** — the `AA_CATALOGUE_<year>` folder of `.docx` files
   (596 files this year). Unzip it somewhere.
2. **AntCat dump** — `worldants.txt` (the tab-delimited export you already
   produce). Unzip it.
3. **AntCat references** — produced by `export_references.rb` on the droplet
   (one extra step, below). The dump has reference *ids* but no bibliography,
   so references are the only category that needs a database pull.

Two old binary `.doc` files ship in the Bolton zip (`CAT-SPECIES CAMPONOTUS a-b.doc`
and the depositories file). Convert any `.doc` to `.docx` first:

```bash
libreoffice --headless --convert-to docx --outdir bolton_docx <folder>/*.doc*
```

(or just point the parser at a folder where everything is already `.docx`).

---

## Run it

```bash
# 1. AntCat side  -> antcat_out/
python3 parse_antcat.py worldants.txt antcat_out

# 2. Bolton side  -> bolton_out/
python3 parse_bolton.py bolton_docx bolton_out

# 3. Diff         -> diff_out/
python3 diff_catalogue.py --antcat-dir antcat_out --bolton-dir bolton_out --out-dir diff_out
```

For references, on the production droplet:

```bash
docker exec -w /app -e RAILS_ENV=production antcat-app \
    bundle exec rails runner /app/export_references.rb
# copies to host: /var/www/antcat-2/antcat_references.csv
```

then re-run the diff with the references wired in:

```bash
python3 diff_catalogue.py --antcat-dir antcat_out --bolton-dir bolton_out \
    --out-dir diff_out --antcat-refs antcat_references.csv
```

`SUMMARY.txt` prints the counts. Everything else lands in `diff_out/`.

---

## The outputs, and what to do with each

### `species_in_bolton_not_antcat.csv` — the main ADD/CHECK list
Every Bolton species-group name with no match in AntCat. The matcher keys on
**(genus, gender-normalised terminal epithet)** and checks the name against
*both* its own combination and AntCat's current-valid combination, so obsolete
combinations don't create false hits. Each row is auto-classified in
`diff_reason`:

- **`new`** — no trace in AntCat. These are the genuine additions (this year:
  6, all 2024–2026 descriptions). **Add to AntCat.**
- **`recombination`** — AntCat has the same taxon (same epithet + year) under a
  **different genus**. Bolton has moved it; AntCat hasn't. The `antcat_has`
  column shows AntCat's current placement. **Verify against the publication,
  then update the combination in AntCat.** (this year: 3 — e.g. Bolton puts
  *henryi* in *Boltonopone*, AntCat still has *Bothroponera henryi*.)
- **`spelling_variant`** — AntCat already has the name under the same genus and
  year but with a slightly different spelling (`antcat_has` shows it). Usually a
  gender ending (*-ense* vs *-ensis*) or a typo on one side. **Check which
  spelling the original publication uses and reconcile.** This catches typos in
  *both* directions — e.g. Bolton's headword `sharjahensiss` (stray double-s)
  vs AntCat's correct `sharjahensis`, and AntCat's `yekzoeae` vs Bolton's
  `yezkoeae`. (this year: 8.)

Rows are sorted new → recombination → spelling_variant. The `original_combination`
and `headword_text` columns give you Bolton's verbatim line for verification.

### `species_in_antcat_not_bolton.csv` — reverse review list
AntCat-**valid** species Bolton does not list as a headword. Sorted **living
first** (`fossil` column); the fossil bulk is expected because Bolton's
genus-group treatment doesn't enumerate fossils. The living names are the ones
worth a look — some mirror the forward findings above, the rest are candidates
where AntCat may have missed a synonymy Bolton applied, or a description Bolton
hasn't yet folded in. Secondary priority. (this year: 873 total, 27 living.)

### `genera_in_bolton_not_antcat.csv`
Bolton genus-group names with no AntCat match. This year all 24 are **invalid**
variant spellings / unjustified emendations (e.g. *Enictus* for *Aenictus*) —
the kind of historical mis-spelling AntCat may or may not choose to track. No
valid genus is missing. The `status` and `classification` columns tell you
which is which.

### `genera_in_antcat_not_bolton.csv`
AntCat-valid genera Bolton doesn't headword. Sorted living-first. This year all
177 are **fossil** — fully expected, nothing to do.

### `references_in_bolton_not_antcat.csv` (only after the refs export)
Bolton bibliography entries with no author+year match in AntCat — i.e.
references to add. Matching is on normalised author-string + year; expect a few
format-driven false positives (accents, *et al.* vs full author lists) that the
year helps you spot. Verify before adding.

---

## Notes / limitations

- The headword epithet carries Bolton's **current** spelling; the binomial on
  the same line is the **original** combination. The matcher uses the headword
  epithet, which is what you want.
- Gender/genitive endings are normalised before matching (`serratulus` ≡
  `serratula`, `lundi` ≡ `lundii`) so legitimate Latin variants don't show up
  as differences. Genuine spelling disagreements still surface as
  `spelling_variant`.
- The diff surfaces disagreements; it does not decide who is right. For
  `recombination` and `spelling_variant` rows the **original publication is the
  authority** — same principle as the type-reconciliation work.
- `parse_antcat.py` skips family/subfamily/tribe rows (no genus, no epithet) so
  they don't pollute the species counts.
- Re-running is idempotent: delete or overwrite the `*_out/` folders and run
  the three scripts again. Nothing touches AntCat.

## Files

```
parse_antcat.py        AntCat dump  -> antcat_out/{species,genera}.csv + keys
parse_bolton.py        Bolton docx  -> bolton_out/{species,genera,references}.csv
diff_catalogue.py      both sides   -> diff_out/*.csv + SUMMARY.txt
export_references.rb   Rails runner -> antcat_references.csv  (run on droplet)
```

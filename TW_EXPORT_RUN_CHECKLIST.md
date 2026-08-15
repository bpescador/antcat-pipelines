# Regenerating the TaxonWorks export files — run checklist

Use this when you need fresh `antcat_references.bib` + `antcat_names.tsv` (e.g. after
staging is updated, or any time AntCat has moved on). One command produces both, but it
needs two inputs pulled from the droplet first.

Legend: **[droplet]** = run on the AntCat server (you're `root@antcat-prod`).
**[mac]** = run in your Mac terminal. **[mac: scripts dir]** = the folder on your Mac
holding the export scripts.

---

## 0. One-time setup on your Mac (skip if already done)

Put these five files in one folder on your Mac — call it `~/antcat-tw/`:

- `build_tw_exports.sh`
- `export_antcat_names.py`
- `export_antcat_bibtex.py`
- `protonym.py`
- `export_references.rb`  (this one gets uploaded to the droplet in step 1)

They're all in the project's `antcat_taxonworks` output folder. Then:

```
[mac]  cd ~/antcat-tw
[mac]  chmod +x build_tw_exports.sh
[mac]  python3 -c "import bibtexparser" 2>/dev/null || pip3 install bibtexparser
```

`bibtexparser` is only used by the script's self-validation step. If you can't install
it, the export still runs; you just lose the built-in parse check (do step 5 manually).

---

## 1. Put the canonical references runner on the droplet

The container reads scripts from `/app`, which is bind-mounted to
`/var/www/antcat-2` on the host. Upload, then confirm the container sees it.

```
[mac]      scp ~/antcat-tw/export_references.rb antcat:/var/www/antcat-2/
[droplet]  docker exec antcat-app ls -la /app/export_references.rb
```

The second line must show the file at `/app/export_references.rb`. If it does, the
runner will find it. (If the `antcat` SSH alias isn't recognised, use
`root@antcat-prod:` in the scp path.)

---

## 2. Export the references (with nested containers) — [droplet]

```
[droplet]  docker exec -w /app -e RAILS_ENV=production antcat-app \
               bundle exec rails runner /app/export_references.rb
```

Read the **last two lines** it prints:

- `Wrote NNNNN references to /app/antcat_references.csv`
- `nested references with a resolved container: 1245`  ← should be ~1,245

**If the container count is near zero, STOP** — the association didn't resolve, and the
`.bib` would have empty containers. Don't proceed; send the output to me.

This only reads the database and writes one CSV. No data is changed.

---

## 3. Pull both inputs to your Mac — [mac]

```
[mac]  scp antcat:/var/www/antcat-2/antcat_references.csv ~/antcat-tw/
```

And a fresh names dump. The dumps are timestamped, so find the newest first:

```
[droplet]  ls -t /var/www/antcat-2/*worldants* | head
[mac]      scp antcat:/var/www/antcat-2/<the-newest-worldants-file> ~/antcat-tw/worldants.txt
```

(Pulling the references and the names on the **same day** is what makes the
name→reference join reach 100% — the two sides agree on which 2026 references exist.)

Quick check the references CSV arrived intact:

```
[mac]  head -1 ~/antcat-tw/antcat_references.csv
```

The header must end with `… nesting_reference_id,nesting_title,nesting_authors,nesting_pages`.
If those four columns are missing, you uploaded/ran the old runner — redo step 1.

---

## 4. Build both files — one command — [mac: scripts dir]

```
[mac]  cd ~/antcat-tw
[mac]  ./build_tw_exports.sh worldants.txt antcat_references.csv tw_out
```

This writes `tw_out/antcat_names.tsv` and `tw_out/antcat_references.bib`, then validates.

---

## 5. Read the validation block — [mac]

The script prints, at the end:

```
== validate the .bib (strict parse, as TaxonWorks' BibTeX-Ruby will) ==
  entries in file / parsed: 12979 / 12979
  unbalanced-brace values:  0
  crossref targets present: True (missing 0)
  RESULT: PASS
== cross-file join check ==
  names: 23090; reference_id -> BibTeX key: 23090 (100.00%)
```

**Ship only if `RESULT: PASS` and the join is ~100%.** The script exits non-zero on any
failure, so if you ever wire it into a larger script it will stop rather than emit a bad
file. If it says FAIL, send me the output — don't hand-edit the `.bib`.

Optional belt-and-braces check with the *actual* Ruby parser TW uses (if you have Ruby):

```
[mac]  gem install bibtex-ruby --user-install
[mac]  ruby -e 'require "bibtex"; b=BibTeX.open("tw_out/antcat_references.bib"); \
           puts "entries: #{b.data.count}, errors: #{b.errors.count}"; \
           b.errors.first(5).each{|e| puts e}'
```

`errors: 0` is the definitive confirmation.

---

## 6. Load into TaxonWorks (staging first)

The DwC-A checklist importer consumes **no citation field**, so references and names
load separately and are linked in a third pass:

1. **Sources** — batch-load `tw_out/antcat_references.bib` via TW's BibTeX Source import.
2. **Names** — load `tw_out/antcat_names.tsv` via the checklist importer.
3. **Link** — the name→Source pass (still to be designed; depends on whether TW exposes
   the `antcat_id` we carry on both sides).

Always staging/sandbox first. Take a TW project SQL export before loading. No deletions.

---

## The short version, once setup is done

```
[mac]      scp ~/antcat-tw/export_references.rb antcat:/var/www/antcat-2/     # only if changed
[droplet]  docker exec -w /app -e RAILS_ENV=production antcat-app \
               bundle exec rails runner /app/export_references.rb            # check container count
[mac]      scp antcat:/var/www/antcat-2/antcat_references.csv ~/antcat-tw/
[mac]      scp antcat:/var/www/antcat-2/<newest-worldants> ~/antcat-tw/worldants.txt
[mac]      cd ~/antcat-tw && ./build_tw_exports.sh worldants.txt antcat_references.csv tw_out
           # ship tw_out/*.tsv and tw_out/*.bib if RESULT: PASS
```

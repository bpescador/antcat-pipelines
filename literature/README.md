# literature: the local library of the primary ant literature

Why (Brian, 13 Nov 2026): part of speech, etymology and spelling history are read from the original
descriptions and from later uses of each name, which means reading most of the primary ant literature,
much of it scanned. Every page is extracted or OCR'd once, kept, and indexed, so it is never fetched or
OCR'd again.

## Where it lives

`~/antcat/literature/` on Brian's Mac. Never in git: the texts are copyrighted, and data never enters
this repo. One folder per AntCat reference id:

| Path | What |
|---|---|
| `pdf/<ref_id>.pdf` | the PDF AntCat holds for the reference |
| `pages/<ref_id>/p0001.txt` | one text file per PDF page, as printed (PDF page order, from 1) |
| `refs.tsv` | one row per reference: citation, year, md5, pages, how many from the text layer, OCR, missing |
| `library.sqlite` | tables `refs` and `pages` (method and language per page) and `pages_fts`, a full-text index |

The index joins words broken at a line end (`crassi-` / `spina`), so searches find them; the page files
keep the text as printed.

## Use

```
python3 literature/search.py --library ~/antcat/literature 'crassispin*'          # every page, oldest first
python3 literature/search.py --library ~/antcat/literature 'crassispin*' --ref 126251
python3 literature/search.py --library ~/antcat/literature --page 126251 5        # read one page
```

OCR has errors: search with a prefix or stem, then read the page or the PDF. A spelling used to decide an
emendation or prevailing usage is always checked in the publication itself.

## Original-description pages

`page_locator.py` finds, for each species-group protonym, the PDF page of its original description: printed page
numbers in each page's first and last lines give the offset to PDF pages; the cited page of the authorship
citation, minus the offset, must carry the epithet (OCR errors allowed). Input: `gender/protonym_pages_export.rb`
(read only, on antcat-prod). Confidence A to F is explained in the script.

```
python3 literature/page_locator.py --library ~/antcat/literature \
    --protonyms ~/antcat/taxonworks_sync/protonym_pages_YYYYMMDD.tsv \
    --references ~/antcat/taxonworks_sync/antcat_references.csv --out page_locator_YYYYMMDD.tsv
```

`--references` (16 Nov 2026): a nested reference (a new species attributed to some of a paper's authors, a
chapter) usually has no PDF of its own in AntCat; its nesting reference has it, and AntCat's own pages link that
PDF. With the references export the locator reads the nesting reference's PDF (column `pdf_ref_id`). On the
14 Nov library this moved 161 names out of class F (148 to A). Another 726 names rest on 254 nesting references
whose PDFs were never fetched: fetch those (`pdfs/stream_reference_pdfs.rb`, `ONLY=` their ids) before the next
library build. Any list of "references without a PDF" must likewise count a nested reference as having its
nesting reference's PDF.

First run, 14 Nov 2026 (24,377 protonyms): A 76.8%, B 1.2%, C 4.4% (82% located), D 2.3%, E 3.0%, F 12.4%
(2,958 have no PDF in AntCat, 62 cite no arabic page).

## Adding papers

```
python3 literature/build_library.py --library ~/antcat/literature --pdf-dir DIR \
    [--ocr-dir DIR] [--refs-tsv refs.tsv] [--ocr --lang eng+deu+fra+ita+spa]
python3 literature/build_library.py --library ~/antcat/literature --pdf FILE --ref-id ID --citation "..." --year YYYY
```

PDF names start with the AntCat reference id and `__` (as `pdfs/fetch_reference_pdfs.rb` writes them).
A page's text comes from the PDF's text layer, else an existing OCR file (`<ref_id>_p<page>.txt`, PDF page
numbers, languages in `languages.tsv`), else new OCR with `--ocr`. Pages with none are recorded as missing; a
later run fills them and keeps everything already done. Re-adding a reference is safe.

## Fetching the PDFs from AntCat

`pdfs/stream_reference_pdfs.rb` (on antcat-prod, read only) sends the PDFs of a list of reference ids from
AntCat's S3 bucket straight off the server as one stream; `pdfs/extract_streamed_pdfs.py` on the Mac writes
them to a folder. Nothing is written on the server, so its 24 GB disk does not limit the batch (13 Nov 2026:
the older `fetch_reference_pdfs.rb` writes to `tmp/` first and took the disk from 62% to 82% for 356 PDFs).

```
# Mac: ids file and script to the server
scp pdfs/stream_reference_pdfs.rb IDS.txt antcat:/var/www/antcat-2/tmp/ && \
ssh antcat 'chmod 644 /var/www/antcat-2/tmp/stream_reference_pdfs.rb /var/www/antcat-2/tmp/IDS.txt'
# Mac: the fetch, one command; per-id log on stderr
caffeinate -i ssh antcat 'docker exec -u antcat -w /app -e RAILS_ENV=production -e ONLY_FILE=tmp/IDS.txt \
  antcat-app bundle exec rails runner tmp/stream_reference_pdfs.rb' 2> stream.log \
  | python3 pdfs/extract_streamed_pdfs.py ~/antcat/literature/incoming/DIR
```

Then check every file's size against `stream.log`, set aside any marked INCOMPLETE (fetch them again), add the
folder with `build_library.py --pdf-dir`, and remove the two files from the server's `tmp/`.

## OCR of scanned pages

OCR languages: the Mac's shell VM has English only; the cloud workspace has German, French, Italian,
Spanish, Portuguese, Dutch, Polish and Russian (Ukrainian Cyrillic reads acceptably as Russian). No Latin.
So scans are OCR'd in the workspace with `ocr_pages.py`, which picks the language once per reference
(Cyrillic script by tesseract's script detection, else the language whose common words win on a sample
page), then imported on the Mac:

```
# workspace: PDFs named <ref_id>.pdf; resumable, skips pages already done
python3 literature/ocr_pages.py --pdf-dir PDFS --out OCR --jobs 2
# Mac: import, in steps that fit the 180 s shell limit
python3 literature/build_library.py --library ~/antcat/literature --pdf-dir ~/antcat/literature/pdf \
    --ocr-dir OCR --skip-existing --max-seconds 150
```

`ref_languages.tsv` in the OCR folder records the language chosen for each reference and why; check it
when a page reads badly. About 1.3 s a page on the workspace's 2 CPUs (13 Nov 2026).

**Best run natively on the Mac** (Terminal, not the agent's shell VM): no 180 s limit, all cores, local disk.
Once: `brew install tesseract tesseract-lang poppler`. Then:

```
cd ~/antcat/antcat-pipelines && caffeinate -i python3 literature/ocr_pages.py --pdf-dir ~/antcat/literature/pdf \
    --out ~/antcat/literature/ocr --jobs 8 > ~/antcat/literature/ocr_run.log 2>&1 && \
python3 literature/build_library.py --library ~/antcat/literature --pdf-dir ~/antcat/literature/pdf \
    --ocr-dir ~/antcat/literature/ocr --skip-existing
```

## The index database

`library.sqlite` is only an index: the PDFs and the page files are the library, and the index can be rebuilt
from them (`--db NEW --refs-tsv refs.tsv`, all references, then move NEW into place). The agent's shell VM sees
the Mac folder as a shared mount on which SQLite's normal locking fails; there, build into a local file with
`--db $HOME/libdb/library.sqlite` and copy it in after each step (copy to `.tmp`, then `mv`). Never write it on
the shared folder with `--shared-folder` in steps that can be cut off: on 14 Nov 2026 a step stopped by the
180 s limit left that index corrupt, and it was rebuilt (3,598 references, 103,962 pages; the corrupt copy is
in `_to_delete/`).

## Scope

The 23,142 species-group names in the 11 Nov 2026 names export were described in 4,114 references
(463 before 1900, 1,486 from 1900 to 1960, 787 from 1961 to 1999, 1,378 since 2000). About 25 GB of PDFs at
the 13 Nov average; the text is a small fraction of that.

## Etymology sources: from match to write (14 Nov 2026)

Where each existing etymology was printed, recorded in AntCat's etymology source fields (source, later-work
reference, printed page; the text is never changed):

1. `gender/protonym_pages_export.rb` (read-only runner) and `literature/page_locator.py`: the PDF page of each
   original description. PeerJ and some other journals number pages "184/462"; those count since 14 Nov (Prebus
   2021b's offset had come out -9).
2. `gender/etymology_sources.py`: each etymology looked for in the original description, then anywhere in the
   library. A printed page only where the paper's offset is carried by at least half its pages (França et al.
   2024 has no page numbers; stray numbers gave +1). A later work must be published after the original.
3. `gender/verify_etymology_sources.py`: the printed page on the page itself, the species (the passage inside the
   name's own account), later works later and not quoting an earlier text (MacKay 2025 quotes Baroni Urbani
   1972). Rows that fail any check are held for the page images; the rest are sampled against page images.
4. `gender/build_etymology_write_input.py`, then `gender/write_etymology_sources.rb` (AntCatBot, staged gates):
   it asserts the etymology text by md5, writes only the three columns, never overwrites, and logs old and new
   values per protonym.

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

## Scope

The 23,142 species-group names in the 11 Nov 2026 names export were described in 4,114 references
(463 before 1900, 1,486 from 1900 to 1960, 787 from 1961 to 1999, 1,378 since 2000). About 25 GB of PDFs at
the 13 Nov average; the text is a small fraction of that.

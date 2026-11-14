#!/usr/bin/env python3
"""
build_library.py -- the local library of the primary ant literature: every PDF AntCat holds for a
reference, split into one text file per page, with a full-text index, so original descriptions can be
found and reread without fetching or OCR-ing them again.

Why: Brian, 13 Nov 2026. Part of speech, etymology and spelling history are read from the original
descriptions (and from every later use of a name), which means reading most of the primary ant
literature, much of it scanned. Each page is extracted or OCR'd once, kept, and indexed.

Layout of the library folder (keep it outside git: the texts are copyrighted, and data never enters git):
  pdf/<ref_id>.pdf            the PDF (hard-linked from where it was found when possible, else copied)
  pages/<ref_id>/p0001.txt    one file per PDF page (PDF page order, from 1), text only
  refs.tsv                    one row per reference (rewritten from the database on every run)
  library.sqlite              tables refs and pages, and pages_fts (FTS5) for searching every page

A page's text comes from, in order: the PDF's own text layer; an existing OCR file for that page
(--ocr-dir, files <ref_id>_p<page>.txt); new OCR (--ocr, tesseract with --lang). Pages with none of
these are recorded as missing, so a later run with --ocr can fill them.

Usage (run where the files are; the AntCat reference id is the part of the PDF name before "__"):
  python3 build_library.py --library ~/antcat/literature --pdf-dir DIR [--ocr-dir DIR] \
      [--refs-tsv spelling_evidence_refs.tsv] [--ocr --lang deu+fra+ita+eng] [--only ID,ID]
  python3 build_library.py --library ~/antcat/literature --pdf FILE --ref-id 126251 --citation "Karavaiev, 1926f" --year 1926
"""
import argparse, csv, datetime, glob, hashlib, os, re, shutil, sqlite3, subprocess, sys, tempfile

MIN_TEXT_CHARS = 60  # a page with less text than this in its text layer is treated as a scan
LINE_BREAK_HYPHEN = re.compile(r'(\w)-[ \t]*\n\s*(\w)')  # "crassi-\nspina" -> "crassispina" (index only)

SCHEMA = """
CREATE TABLE IF NOT EXISTS refs (ref_id INTEGER PRIMARY KEY, citation TEXT, year TEXT, pdf TEXT, md5 TEXT,
  pages INTEGER, text_layer_pages INTEGER, ocr_pages INTEGER, missing_pages INTEGER, added TEXT);
CREATE TABLE IF NOT EXISTS pages (ref_id INTEGER, page INTEGER, method TEXT, lang TEXT, chars INTEGER,
  PRIMARY KEY (ref_id, page));
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(text, ref_id UNINDEXED, page UNINDEXED,
  tokenize = 'unicode61 remove_diacritics 2');
"""


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def pdf_page_count(path):
    out = subprocess.run(['pdfinfo', path], capture_output=True, text=True).stdout
    m = re.search(r'^Pages:\s+(\d+)', out, re.M)
    return int(m.group(1)) if m else 0


def text_layer_pages(path, n):
    out = subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', path, '-'], capture_output=True).stdout
    parts = out.decode('utf-8', 'replace').split('\f')
    return [(parts[i] if i < len(parts) else '') for i in range(n)]


def ocr_page(path, page, lang, timeout):
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, 'p')
        subprocess.run(['pdftoppm', '-r', '300', '-gray', '-png', '-f', str(page), '-l', str(page), '-singlefile', path, base],
                       check=True, timeout=timeout)
        env = dict(os.environ, OMP_THREAD_LIMIT='1')
        try:
            res = subprocess.run(['tesseract', base + '.png', '-', '-l', lang], capture_output=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return ''
        return res.stdout.decode('utf-8', 'replace')


def place_pdf(src, dst, link):
    if os.path.exists(dst) and md5(dst) == md5(src):
        return
    if os.path.exists(dst):
        sys.exit(f'{dst} exists with different content; not overwriting (compare {src})')
    if link:
        try:
            os.link(src, dst)
            return
        except OSError:
            pass
    shutil.copy2(src, dst)


def add_reference(db, lib, ref_id, pdf, citation, year, ocr_files, do_ocr, lang, timeout, link):
    os.makedirs(os.path.join(lib, 'pdf'), exist_ok=True)
    page_dir = os.path.join(lib, 'pages', str(ref_id))
    os.makedirs(page_dir, exist_ok=True)
    dst = os.path.join(lib, 'pdf', f'{ref_id}.pdf')
    place_pdf(pdf, dst, link)
    n = pdf_page_count(dst)
    layer = text_layer_pages(dst, n)
    old = {p: (m, l) for p, m, l in db.execute('SELECT page, method, lang FROM pages WHERE ref_id = ?', (ref_id,))}
    counts = {'text layer': 0, 'ocr': 0, 'missing': 0}
    for i in range(1, n + 1):
        text, method, used_lang = layer[i - 1], 'text layer', ''
        if len(text.strip()) < MIN_TEXT_CHARS:
            path = os.path.join(page_dir, f'p{i:04d}.txt')
            if i in ocr_files:
                text, method, used_lang = open(ocr_files[i], encoding='utf-8', errors='replace').read(), 'ocr', 'eng'
            elif old.get(i, ('',))[0] == 'ocr' and os.path.exists(path):
                text, method, used_lang = open(path, encoding='utf-8').read(), 'ocr', old[i][1]
            elif do_ocr:
                text, method, used_lang = ocr_page(dst, i, lang, timeout), 'ocr', lang
            else:
                text, method = '', 'missing'
        with open(os.path.join(page_dir, f'p{i:04d}.txt'), 'w', encoding='utf-8') as f:
            f.write(text)
        counts['missing' if method == 'missing' else method] += 1
        db.execute('INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?)', (ref_id, i, method, used_lang, len(text.strip())))
        db.execute('DELETE FROM pages_fts WHERE ref_id = ? AND page = ?', (ref_id, i))
        if text.strip():
            # The page file keeps the text as printed; the index joins words broken at a line end, so a
            # search for "crassispina" finds "crassi-" + "spina" (Karavaiev 1926f: 69).
            db.execute('INSERT INTO pages_fts (text, ref_id, page) VALUES (?,?,?)',
                       (LINE_BREAK_HYPHEN.sub(r'\1\2', text), ref_id, i))
    row = db.execute('SELECT citation, year, added FROM refs WHERE ref_id = ?', (ref_id,)).fetchone()
    db.execute('INSERT OR REPLACE INTO refs VALUES (?,?,?,?,?,?,?,?,?,?)',
               (ref_id, citation or (row and row[0]) or '', year or (row and row[1]) or '', f'pdf/{ref_id}.pdf', md5(dst), n,
                counts['text layer'], counts['ocr'], counts['missing'],
                (row and row[2]) or datetime.date.today().isoformat()))
    return counts


def write_refs_tsv(db, lib):
    cols = ['ref_id', 'citation', 'year', 'pdf', 'md5', 'pages', 'text_layer_pages', 'ocr_pages', 'missing_pages', 'added']
    with open(os.path.join(lib, 'refs.tsv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter='\t', lineterminator='\n')
        w.writerow(cols)
        w.writerows(db.execute(f'SELECT {",".join(cols)} FROM refs ORDER BY ref_id'))


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument('--library', required=True)
    a.add_argument('--pdf-dir'); a.add_argument('--pdf'); a.add_argument('--ref-id', type=int)
    a.add_argument('--citation'); a.add_argument('--year')
    a.add_argument('--ocr-dir', help='existing OCR pages named <ref_id>_p<page>.txt (PDF page numbers)')
    a.add_argument('--refs-tsv', help='TSV with reference_id, citation, year columns (spelling_evidence_refs.tsv)')
    a.add_argument('--ocr', action='store_true', help='OCR pages that have neither a text layer nor an OCR file')
    a.add_argument('--lang', default='eng+deu+fra+ita+spa', help='tesseract languages for --ocr')
    a.add_argument('--timeout', type=int, default=120)
    a.add_argument('--only', help='comma-separated reference ids')
    a.add_argument('--copy', action='store_true', help='copy PDFs instead of hard-linking them')
    o = a.parse_args()
    lib = os.path.expanduser(o.library)
    os.makedirs(lib, exist_ok=True)
    db = sqlite3.connect(os.path.join(lib, 'library.sqlite'))
    db.executescript(SCHEMA)

    meta = {}
    if o.refs_tsv:
        for r in csv.DictReader(open(o.refs_tsv, encoding='utf-8'), delimiter='\t'):
            meta[int(r['reference_id'])] = (r.get('citation', ''), r.get('year', ''))
    ocr = {}
    if o.ocr_dir:
        for p in glob.glob(os.path.join(o.ocr_dir, '*_p*.txt')):
            m = re.match(r'(\d+)_p(\d+)\.txt$', os.path.basename(p))
            if m:
                ocr.setdefault(int(m.group(1)), {})[int(m.group(2))] = p
    jobs = []
    if o.pdf:
        if not o.ref_id:
            sys.exit('--pdf needs --ref-id')
        jobs.append((o.ref_id, o.pdf))
    if o.pdf_dir:
        for p in sorted(glob.glob(os.path.join(o.pdf_dir, '*.pdf'))):
            m = re.match(r'(\d+)__', os.path.basename(p))
            if m:
                jobs.append((int(m.group(1)), p))
    only = {int(x) for x in o.only.split(',')} if o.only else None
    totals = {'refs': 0, 'text layer': 0, 'ocr': 0, 'missing': 0}
    for ref_id, pdf in jobs:
        if only and ref_id not in only:
            continue
        cit, yr = meta.get(ref_id, ('', ''))
        c = add_reference(db, lib, ref_id, pdf, o.citation or cit, o.year or yr, ocr.get(ref_id, {}),
                          o.ocr, o.lang, o.timeout, not o.copy)
        db.commit()
        totals['refs'] += 1
        for k in c:
            totals[k] += c[k]
        print(f'{ref_id}\t{os.path.basename(pdf)}\ttext layer {c["text layer"]}\tocr {c["ocr"]}\tmissing {c["missing"]}', flush=True)
    write_refs_tsv(db, lib)
    n_refs, n_pages = db.execute('SELECT COUNT(*), SUM(pages) FROM refs').fetchone()
    print(f'this run: {totals}')
    print(f'library: {n_refs} references, {n_pages or 0} pages; {lib}')


if __name__ == '__main__':
    main()

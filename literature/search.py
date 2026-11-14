#!/usr/bin/env python3
"""
search.py -- search every page in the literature library (build_library.py) and print where a word
occurs: reference id, citation, PDF page, method (text layer or OCR) and a snippet.

Usage:
  python3 search.py --library ~/antcat/literature 'crassispin*'          # FTS5 query; * = prefix
  python3 search.py --library ~/antcat/literature 'crassispin*' --ref 126251
  python3 search.py --library ~/antcat/literature --page 126251 3        # print one page

OCR text has errors, so search with a prefix or a short stem, and read the page (or the PDF) before
relying on a spelling: a decisive spelling is always checked in the publication.
"""
import argparse, os, sqlite3, sys


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument('--library', required=True)
    a.add_argument('query', nargs='?')
    a.add_argument('--ref', type=int)
    a.add_argument('--page', nargs=2, type=int, metavar=('REF_ID', 'PAGE'))
    a.add_argument('--limit', type=int, default=50)
    o = a.parse_args()
    lib = os.path.expanduser(o.library)
    if o.page:
        print(open(os.path.join(lib, 'pages', str(o.page[0]), f'p{o.page[1]:04d}.txt'), encoding='utf-8').read())
        return
    if not o.query:
        sys.exit('give a query or --page')
    # read only and immutable: no locks, which the shared Mac folder does not support (build_library.py)
    db = sqlite3.connect(f"file:{os.path.join(lib, 'library.sqlite')}?mode=ro&immutable=1", uri=True)
    sql = ("SELECT f.ref_id, f.page, r.citation, p.method, snippet(pages_fts, 0, '[', ']', ' ... ', 12) "
           "FROM pages_fts f JOIN refs r ON r.ref_id = f.ref_id JOIN pages p ON p.ref_id = f.ref_id AND p.page = f.page "
           "WHERE pages_fts MATCH ?")
    args = [o.query]
    if o.ref:
        sql += ' AND f.ref_id = ?'
        args.append(o.ref)
    sql += ' ORDER BY r.year, f.ref_id, f.page LIMIT ?'
    args.append(o.limit)
    for ref_id, page, cit, method, snip in db.execute(sql, args):
        print(f'{ref_id}\tp{page}\t{cit}\t{method}\t{" ".join(snip.split())}')


if __name__ == '__main__':
    main()

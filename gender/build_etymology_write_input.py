#!/usr/bin/env python3
"""
build_etymology_write_input.py -- the input file of gender/write_etymology_sources.rb.

Takes the rows of verify_etymology_sources.py with verdict 'ok' (word-for-word matches with a confidently
established printed page, original description or later work) and writes, per protonym: the name, the source, the
reference (the authorship reference for an original description, which the runner checks; the later work's
otherwise), the printed page, and the md5 of the etymology text as exported (the runner holds a protonym whose text
has changed since). Everything held (no page, verdict 'check', near/partial/mismatch, not found) stays out.

Inputs: --verify (verify_etymology_sources.py output), --protonyms (protonym_pages export), --out.
Standard library only.
"""
import argparse, collections, csv, hashlib, re, sys

csv.field_size_limit(sys.maxsize)


def clean(value):
    return re.sub(r'[\t\r\n]+', ' ', value or '')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--verify', required=True)
    ap.add_argument('--protonyms', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    with open(a.protonyms, newline='', encoding='utf-8') as fh:
        export = {r['protonym_id']: r for r in csv.DictReader(fh, delimiter='\t')}
    with open(a.verify, newline='', encoding='utf-8') as fh:
        rows = [r for r in csv.DictReader(fh, delimiter='\t') if r['verdict'] == 'ok']
    counts = collections.Counter()
    with open(a.out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n', quoting=csv.QUOTE_NONE, escapechar='\\')
        w.writerow(['protonym_id', 'protonym_name', 'source', 'reference_id', 'pages', 'etymology_md5'])
        for r in rows:
            x = export[r['protonym_id']]
            assert not (x['etymology_source'] or x['etymology_reference_id'] or x['etymology_pages']), r['protonym_id']
            source = r['source']
            ref = r['reference_id'] if source == 'later_work' else x['authorship_reference_id']
            assert ref and r['pages'].strip(), r['protonym_id']
            md5 = hashlib.md5(clean(x['etymology_taxt']).encode('utf-8')).hexdigest()
            w.writerow([r['protonym_id'], x['protonym_name'], source, ref, r['pages'].strip(), md5])
            counts[source] += 1
    for k in sorted(counts):
        print(k, counts[k])
    print('rows', sum(counts.values()))


if __name__ == '__main__':
    main()

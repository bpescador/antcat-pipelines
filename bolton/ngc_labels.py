#!/usr/bin/env python3
"""
ngc_labels.py -- draft AntCat's own labels for type fields that still carry NGC-style ones.
READ ONLY: writes a CSV of the current and drafted text; nothing is written to AntCat.

  python3 bolton/ngc_labels.py PROTONYMS.jsonl OUT.csv

About 1,200 protonyms (8 Nov 2026) still use the NGC's labels ("Type-material:",
"Type-depository:", "Paratype-depositories:") instead of AntCat's ("Primary type material:",
"Secondary type depositories:"). The drafting rule, for Bradley to agree before any write:

  primary field   (primary_type_information_taxt):   Type-X              -> Primary type X
  secondary field (secondary_type_information_taxt): Paratype-X, Type-X  -> Secondary type X
  X = material, locality, localities, depository, depositories, specimen, specimens

Agreed by Bradley 2026-11-10 for the hyphenated (NGC) labels only. Labels WITHOUT a hyphen
("Type depositories:", "Type locality:") are AntCat's own and intentional: they are used where
the data cannot be split into primary and secondary (e.g. the holotype's depository is not
known), and the same text stands in both fields. They are never changed; they are listed with
the flag "space-form label kept" so a person can check that a note explains them.

Only a label at the start of the field or of a sentence is changed; every other character
stays. Type notes are not changed: a label there is listed with a flag.

Flags (the row is still drafted; a person looks at it):
  - "paratypes in the primary field": the primary material names paratypes, which belong in
    the secondary field (Bradley: an AntCat error, to split by hand);
  - "also a space-form label (kept)": the field has both kinds; only the hyphenated ones change;
  - "space-form label kept: check that a note explains": nothing drafted;
  - "label in type notes".

Output columns: protonym_id, name, author, year, field, labels, current, draft, flag, url.
Input: bolton/export_protonyms.rb output (protonyms_species_typeinfo.jsonl, plain or .gz).
"""
import csv, gzip, json, re, sys
from collections import Counter

X = r'(material|localit(?:y|ies)|depositor(?:y|ies)|specimens?)'
START = r'(?:^|(?<=[.;]\s))'
PRIMARY = re.compile(START + r'Type-' + X + r':')
SECONDARY = re.compile(START + r'(?:Paratype|Type)-' + X + r':')
SPACE = re.compile(START + r'Type ' + X + r':')   # AntCat's own: kept
FIELDS = [('primary_type_taxt', 'primary', PRIMARY, 'Primary type '),
          ('secondary_type_taxt', 'secondary', SECONDARY, 'Secondary type ')]


def strip_labels(t):
    """text with every label removed, NGC-style or AntCat's: the draft must equal the current text here"""
    return re.sub(START + r'(?:(?:Primary|Secondary) type |Paratype-|Type[- ])' + X + r':', ':', t)


def draft(text, rx, prefix):
    labels = [m.group(0) for m in rx.finditer(text)]
    new = rx.sub(lambda m: prefix + m.group(1) + ':', text)
    assert strip_labels(new) == strip_labels(text), 'a character other than a label changed'
    return new, labels


def main():
    src, out = sys.argv[1], sys.argv[2]
    op = gzip.open if src.endswith('.gz') else open
    rows, n_rec = [], 0
    with op(src, 'rt', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            p = json.loads(line)
            hit = False
            for key, field, rx, prefix in FIELDS:
                t = p.get(key) or ''
                new, labels = draft(t, rx, prefix)
                kept = [m.group(0) for m in SPACE.finditer(t)]
                if not labels and not kept:
                    continue
                hit = True
                flag = []
                if not labels:
                    flag.append('space-form label kept: check that a note explains')
                    labels = kept
                elif kept:
                    flag.append('also a space-form label (kept)')
                if labels is not kept and field == 'primary' and re.search(r'material:[^.]*paratype', new, re.I):
                    flag.append('paratypes in the primary field')
                rows.append(dict(protonym_id=p['protonym_id'], name=p.get('name'), author=p.get('author'),
                                 year=p.get('year'), field=field, labels='; '.join(labels), current=t,
                                 draft=new, flag='; '.join(flag),
                                 url=f"https://antcat.org/protonyms/{p['protonym_id']}"))
            notes = p.get('type_notes_taxt') or ''
            nl = [m.group(0) for m in SECONDARY.finditer(notes)]
            if nl:
                hit = True
                rows.append(dict(protonym_id=p['protonym_id'], name=p.get('name'), author=p.get('author'),
                                 year=p.get('year'), field='type notes', labels='; '.join(nl), current=notes,
                                 draft=notes, flag='label in type notes',
                                 url=f"https://antcat.org/protonyms/{p['protonym_id']}"))
            n_rec += hit
    cols = ['protonym_id', 'name', 'author', 'year', 'field', 'labels', 'current', 'draft', 'flag', 'url']
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    lab = Counter((r['field'], l) for r in rows for l in r['labels'].split('; '))
    drafted = {r['protonym_id'] for r in rows if r['draft'] != r['current']}
    print(f"{n_rec} protonyms listed, {len(drafted)} with a drafted change; {len(rows)} fields -> {out}")
    for (fld, l), k in lab.most_common():
        print(f"  {k:5}  {fld:10} {l}")
    print(f"  flagged: {Counter(r['flag'] for r in rows if r['flag'])}")


if __name__ == '__main__':
    main()

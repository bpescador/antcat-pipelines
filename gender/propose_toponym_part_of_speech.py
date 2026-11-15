#!/usr/bin/env python3
"""
propose_toponym_part_of_speech.py -- part of speech for the toponym derivations (pattern-by-pattern plan,
approved by Brian 14 Nov 2026 21:43).

Brian: "A verified geographic stem combined with the Latin adjectival suffix -ensis supports classification as
an adjective. Record basis 'grammatical form' and status 'demonstrated' when the construction is unambiguous.
Test -anus and -icus separately rather than automatically treating every matching ending as adjectival. Do not
rewrite existing derivations simply to add grammatical metadata."

So, for each name whose AntCat derivation is a toponym (the rows of gender/propose_toponym_derivations.py
--write-input that were written):
  - suffix -ensis, epithet ending -ensis or -ense, no sourced etymology, part of speech blank (or already
    adjective), interpretation blank (or already demonstrated): proposed under rule toponym_ensis_pos
    (adjective; grammatical_form; demonstrated) -- written only by gender/write_protonym_fields.rb;
  - suffix -anus: listed for Brian's separate test (--anus-review), never proposed here;
  - anything else: held with the reason.

Inputs: --protonyms (gender/protonym_pages_export.rb TSV), --derivations (the derivation write input).
Outputs: --out (every row with result and reason), --write-input (rows for write_protonym_fields.rb),
--anus-review. Standard library only; read only.
"""
import argparse, collections, csv, re, sys

csv.field_size_limit(sys.maxsize)
RULE = 'toponym_ensis_pos'
FIELDS = [('gender_agreement_type', 'adjective'), ('part_of_speech_basis', 'grammatical_form'),
          ('interpretation_status', 'demonstrated')]


def read_tsv(path, quoting=csv.QUOTE_MINIMAL):
    with open(path, encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh, delimiter='\t', quoting=quoting))


def classify(d, p):
    """-> (group, reason): group is 'ensis', 'anus' or 'held'."""
    m = re.search(r'Formed from (?:the )?(.+?) with the Latin adjectival suffix <i>(-ensis|-anus)</i>', d['derivation'])
    if not m:
        return 'held', 'not a toponym derivation of the pilot form'
    suffix = m.group(2)
    if suffix == '-anus':
        return 'anus', 'suffix -anus: tested separately (Brian, 21:43)'
    if not re.search(r'(ensis|ense)$', p['epithet']):
        return 'held', f"epithet {p['epithet']} does not end in -ensis or -ense"
    if p['etymology_taxt'].strip():
        return 'held', 'has a sourced etymology'
    if p['part_of_speech'] not in ('', 'adjective'):
        return 'held', f"part of speech is {p['part_of_speech']}"
    if p['interpretation_status'] not in ('', 'demonstrated'):
        return 'held', f"interpretation is {p['interpretation_status']}"
    return 'ensis', ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--protonyms', required=True)
    ap.add_argument('--derivations', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--write-input')
    ap.add_argument('--anus-review')
    a = ap.parse_args()

    prot = {r['protonym_id']: r for r in read_tsv(a.protonyms)}
    ders = read_tsv(a.derivations, quoting=csv.QUOTE_NONE)
    out, counts = [], collections.Counter()
    for d in ders:
        p = prot.get(d['protonym_id'])
        if not p:
            group, reason = 'held', 'not in the protonym export'
        elif p['protonym_name'] != d['protonym_name']:
            group, reason = 'held', f"name differs ({p['protonym_name']})"
        else:
            group, reason = classify(d, p)
        counts[group if group != 'held' else 'held: ' + reason.split(' (')[0]] += 1
        out.append((d, p, group, reason))

    with open(a.out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['protonym_id', 'protonym_name', 'epithet', 'terminal_taxon_name', 'part_of_speech',
                    'interpretation_status', 'group', 'reason', 'derivation'])
        for d, p, group, reason in out:
            w.writerow([d['protonym_id'], d['protonym_name'], p['epithet'] if p else '',
                        p['terminal_taxon_name'] if p else '', p['part_of_speech'] if p else '',
                        p['interpretation_status'] if p else '', group, reason, d['derivation']])
    if a.write_input:
        with open(a.write_input, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh, delimiter='\t', lineterminator='\n', quoting=csv.QUOTE_NONE, escapechar='\\')
            w.writerow(['protonym_id', 'protonym_name', 'rule', 'field', 'value', 'locality_md5'])
            for d, p, group, reason in out:
                if group == 'ensis':
                    for field, value in FIELDS:
                        w.writerow([d['protonym_id'], d['protonym_name'], RULE, field, value, d['locality_md5']])
    if a.anus_review:
        with open(a.anus_review, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh, delimiter='\t', lineterminator='\n')
            w.writerow(['protonym_id', 'protonym_name', 'author_citation', 'epithet', 'terminal_taxon_name',
                        'locality', 'part_of_speech', 'derivation'])
            for d, p, group, reason in out:
                if group == 'anus':
                    w.writerow([d['protonym_id'], d['protonym_name'], p['author_citation'], p['epithet'],
                                p['terminal_taxon_name'], p['locality'], p['part_of_speech'], d['derivation']])
    for k in sorted(counts):
        print(f'{counts[k]:5d}  {k}')
    print('derivations', len(out))


if __name__ == '__main__':
    main()
